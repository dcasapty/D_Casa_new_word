# Brian — el asistente de D'CASA (plan y contrato)

Brian es el asistente de IA del panel administrativo. Conversa en español, entiende la
pantalla donde está el administrador, consulta todo (ventas, inventario, clientes,
contabilidad, socios, usuarios) y, con su habilidad **el constructor**, crea y edita
registros dentro de reglas claras. Está en tres canales con **un solo catálogo de
herramientas**:

| Canal | Dónde | Quién |
|---|---|---|
| Chat en el panel | Botón flotante en todas las pantallas (Ctrl + J) | Usuarios internos |
| Telegram | Bot propio; se vincula con un código de un solo uso | Administradores vinculados |
| MCP | `POST /brian/mcp` (Streamable HTTP, JSON-RPC 2.0), clave de API de Odoo | Clientes MCP (Claude Desktop, etc.) |

## Arquitectura (módulo `dcasa_brian`)

```
chat (OWL) ─┐
Telegram ───┼─> brian.conversacion ─> proveedor de IA (Claude / OpenAI-compatible / prueba)
MCP ────────┘         │                        │  tool calls
                      └──> brian.herramientas.ejecutar() ─> brian.politica ─> herramienta
                                         │                                      (como el usuario)
                                         └─> brian.accion (registro de auditoría)
```

* **`registro.py`** — decorador `@herramienta`, catálogo, preselección de herramientas por
  mensaje, ejecución con savepoint, confirmación humana. Es el contrato; ver su docstring.
* **`politica.py`** — lo que Brian no puede hacer aunque se lo pidan (lista abajo).
* **`accion.py`** — `brian.accion`: cada herramienta ejecutada, con usuario, canal,
  argumentos, resultado y estado (hecha, error, bloqueada, por confirmar, rechazada).
* **`proveedores.py`** — adaptadores: Anthropic (Claude), OpenAI-compatible (ChatGPT,
  Grok/xAI, Llama vía Groq/Together/OpenRouter, Ollama local) y `prueba` (guion fijo para
  tests). Configuración por variables de entorno (secretos de Cloudflare), nunca en Git.
* **`conversacion.py`** — hilo, mensajes, adjuntos, bucle agente (pensar → herramienta →
  observar) con límite de pasos y de tokens; `_PasosEnVivo` cuenta cada paso al navegador por el
  bus; `estado_panel()` arma las pastillas de la cabecera.
* **`pasos.py`** — funciones puras: el título humano de un paso («Buscando productos «888K»»), el
  resumen corto del resultado y el detalle expandible. Nunca inventa: texto, conteo o «Listo».
* **`herramientas_*.py`** — las capacidades, por área.

## Niveles de permiso

| Nivel | Ejemplos | Comportamiento |
|---|---|---|
| lectura | reporte del día, buscar productos, balance, clientes que deben | Directo |
| construcción | crear producto, cliente, cotización, factura en borrador; editar precio; mover stock | Directo, auditado |

`crear_cliente` pide el celular y el correo, los dos bien escritos (los mismos «¿Quisiste decir…?» de la ficha); si
el cliente de verdad no tiene correo, se escribe «no tiene» y queda marcada «Cliente no tiene correo electrónico».
`actualizar_cliente` revisa igual el celular y el correo (y acepta el correo «no tiene»).
| sensible | confirmar una venta, publicar una factura, registrar un pago, cambiar el rol de un usuario, archivar | Brian propone → el humano pulsa **Permitir** (o **Rechazar**) en una tarjeta con el detalle exacto |
| prohibido | ver abajo | No existe herramienta para eso |

### Lo que Brian nunca hace

1. Eliminar, archivar o quitarle permisos al administrador, ni a sí mismo (el usuario con quien conversa).
2. Modificar facturas publicadas o pagadas, asientos publicados ni conciliaciones: eso se corrige con notas de crédito o asientos contrarios, por una persona.
3. Borrar (unlink) registros contables, del libro de puntos (`dcasa.movimiento`) o del registro de acciones de Brian.
4. Tocar el programa Socios o el de vendedores fuera de sus reglas (cifras solo de `puntos.json`; el libro no se edita).
5. Ver o cambiar contraseñas, claves de API, `DCASA_PIN_PEPPER` ni parámetros técnicos del sistema.
6. Ejecutar código, SQL o acciones del servidor arbitrarias.
7. Actuar con más permisos que el usuario: todo corre como él.

## Modelos pequeños primero

Brian debe funcionar bien con modelos económicos (Claude Haiku, GPT-4o-mini, Llama 3.x
8B/70B, Grok mini) y mejor con los grandes:

* Herramientas con verbo + objeto en español, pocos parámetros, tipos simples, ejemplos.
* **Preselección**: con un modelo pequeño (haiku, mini, 8b…) o `BRIAN_HERRAMIENTAS_MAX`, por
  mensaje se ofrecen solo las ~12 herramientas más relevantes; las generales (pantalla actual,
  ayuda, buscar) ocupan como mucho un tercio de los cupos. Con modelos grandes, todas.
* Resultados compactos y ya formateados (montos con $, fechas dd/mm/aaaa), sin IDs sueltos.
* Errores en español que dicen cómo corregir; el bucle permite reintentar.
* Instrucciones del sistema cortas, con el contexto de la pantalla y la fecha de Panamá.
* Informes deterministas: las cifras las calcula Odoo, no el modelo.

## Seguridad

* Cada canal autentica al usuario de Odoo (sesión, clave de API con alcance, o vínculo de
  Telegram por código de un solo uso) y todo se ejecuta con sus permisos.
* Contenido de adjuntos, correos, descripciones y registros es **dato**, nunca instrucción
  (defensa contra inyección de prompts): va marcado como tal al modelo. Las marcas del bloque
  (`<<…>>`) y etiquetas tipo `</system>` escritas dentro de un archivo o en su nombre se
  neutralizan: un adjunto no puede «cerrar» su bloque de datos.
* **Lo que se construye a partir de adjuntos pide confirmación**: en un turno cuyo mensaje trae
  archivos o fotos, toda herramienta de construcción (crear cliente, cotización, factura, cambiar
  precio…) queda «por confirmar» como una sensible. Excepción: las que solo dejan un borrador
  revisable, marcadas `segura_con_adjuntos=True` (hoy `proponer_importacion`). La acción queda con
  `con_adjuntos` en el registro.
* **Dura más de un turno** (ronda 8): el turno cuenta como «con adjuntos» si alguno de los **últimos 6 mensajes** de la persona trae
  un archivo (el texto del adjunto sigue a la vista del modelo; un «ok, sigue» no quita la defensa).
* **Texto que escribió un cliente** (`@herramienta(texto_externo=True)`, hoy `oportunidades_abiertas`): una vez usada una herramienta
  así en el turno, las de construcción también piden confirmación («acabo de leer textos que escribieron clientes…»).
* **Tamaño de lo que manda el modelo**: hasta 10 000 letras por dato y 30 000 entre todos, revisado **antes** de registrar la llamada
  (si no, la auditoría —que no se puede borrar— se infla). `leer_lineas` rechaza líneas de más de 300 letras.
* **Tope de gasto de IA** (*Ajustes › Brian*): dólares por mes (hora de Panamá), uno para **todos** y uno **por persona**.
  **De fábrica NO hay tope (0):** la cifra la pone la dueña, y el límite que ponga en el panel de su proveedor de IA es el freno
  más fuerte (está fuera del código). Al llegar, Brian lo dice con claridad y no llama al modelo; una acción
  por confirmar sigue pendiente hasta que haya cupo. Cuenta el costo estimado con la tarifa pública (`brian.uso`); un modelo sin
  tarifa se cuenta con la más cara que conocemos, así que un modelo nuevo no deja el tope ciego. No es un presupuesto: es la red
  para una clave filtrada o un script que repite mensajes.
* **Tamaño de lo que se manda**: hasta 8 000 letras por mensaje (un documento largo va como adjunto) y 5 archivos por mensaje.
* **Telegram, lista de chats permitidos** (`BRIAN_TELEGRAM_CHATS`): con la lista puesta, Brian solo atiende y solo le escribe a esos
  chats; de cualquier otro **no contesta nada** (ni las instrucciones para vincularse) y nadie puede vincularse desde otro chat.
  Detalle en «Conectar el Telegram de la gerencia».
* **Telegram**: el vínculo se revisa en cada mensaje y botón; un usuario archivado (o que ya no es interno) pierde su chat al instante.
* Límite de pasos por turno y de mensajes por minuto por usuario.
* Las claves (`BRIAN_API_KEY`, `TELEGRAM_BOT_TOKEN`) viven como secretos de Cloudflare /
  GitHub Actions; **nunca en el repositorio**.

## Historial: renombrar, borrar y retención

En el panel, cada fila de «Conversaciones anteriores» trae **Renombrar** (en línea: Enter
guarda, Esc cancela) y **Borrar** (pide confirmación). También se borra desde Menú › Brian ›
Conversaciones. Cada quien renombra y borra **solo las suyas** (ni el administrador toca las
ajenas desde la interfaz).

Borrar es **borrado real** (decisión del dueño):

| Dato | Qué pasa |
|---|---|
| Conversación, mensajes y sus adjuntos (`ir.attachment` de la conversación) | Se borran. |
| Registro de acciones `brian.accion` | **Se conserva** (auditoría inmutable) con la conversación en blanco. |
| Acciones «por confirmar» de esa conversación | Pasan a «rechazada»: un botón viejo de Telegram ya no las ejecuta. |
| Adjuntos de otros registros citados en el chat | Se quedan en su registro. |
| Telegram con esa conversación activa | El siguiente mensaje abre una nueva. |

El servidor avisa al navegador del dueño por el bus (`dcasa_brian/conversacion_borrada`,
`dcasa_brian/conversacion_cambiada`): el panel quita la fila al momento, y si la conversación
abierta se borró, sigue en una nueva conservando lo escrito. Si el bus no conecta, el panel
vuelve a comprobar al regresar a la pestaña.

El dueño y el canal de una conversación no se cambian después de crearla, y un mensaje no se
muda de conversación (cierra la puerta a «regalarle» un historial fabricado a otra persona).

**Retención** (cron mensual «Brian: borrar conversaciones viejas y adjuntos huérfanos»):

* Borra, por el mismo camino que el botón, las conversaciones sin actividad hace más de
  `dcasa_brian.retencion_dias` días (Ajustes › Técnico › Parámetros del sistema; por defecto
  **180**; **0 = nunca**).
* Borra los adjuntos subidos a Brian cuya conversación/mensaje ya no existe, y los que llevan
  más de un día sin enviarse en ningún mensaje (subidos y quitados antes de enviar).

## Brian en vivo: pasos, permisos y pastillas

### Ver a Brian trabajar (pasos en tiempo real)

Mientras `enviar` / `confirmar_accion` corren, el panel ya no muestra solo «Brian está
pensando…»: pinta la lista de pasos del turno a medida que ocurren («Pensando…», «Leyendo adjunto
«42»», «Buscando productos «888K» — 3 productos», con lo que tardó cada uno) y, al terminar, los
mismos pasos quedan en «Usó N herramientas», cada uno con **Ver resultado** (el JSON compacto,
recortado a 600 caracteres).

* **Por qué el bus de Odoo y no SSE**: el módulo ya usa el bus para avisar borrados y renombres
  (`dcasa_brian/conversacion_borrada`, `…_cambiada`), el cliente web ya está suscrito al canal del
  usuario y el Worker de Cloudflare ya pasa el websocket. SSE habría exigido una ruta HTTP nueva, un
  segundo *stream* abierto por turno y configurar el borde para no cortarlo; además el bucle agente
  sigue dentro de la petición RPC, que ya devuelve la respuesta completa. **No cambia el proveedor
  de IA ni la política**: lo que viaja son metadatos del turno (títulos, resúmenes cortos,
  duraciones), nunca el prompt ni la respuesta del modelo.
* **Cómo**: `_PasosEnVivo` (en `conversacion.py`) manda por `dcasa_brian/pasos` la lista
  **completa** de pasos en cada cambio (idempotente: el panel la reemplaza), con `turno` = id del
  mensaje que lo disparó. Se emite con un **cursor aparte y commit inmediato**: `bus.bus` escribe en
  el *precommit* y notifica en el *postcommit*, así que dentro de la transacción del RPC nada
  llegaría hasta el final (ese cursor aparte usa el superusuario solo para escribir la fila del bus;
  el destino es siempre el partner del dueño de la conversación). Solo canal `chat` (Telegram y MCP reciben la respuesta por su canal).
  Si el bus falla, el turno sigue igual: la respuesta completa llega por el RPC.
* Formato: ver el docstring de `models/conversacion.py` (`paso = {id, tipo: modelo|herramienta,
  nombre, titulo, estado: en_curso|ok|error|por_confirmar, resumen, detalle, duracion_ms}`).

### Tarjeta Permitir / Rechazar (acciones sensibles)

La tarjeta de una acción sensible (o de construcción en un turno con adjuntos) trae el resumen de
la política **más el detalle exacto**, campo por campo, de los argumentos registrados en
`brian.accion` (`_detalle_accion`): son los mismos que `brian.herramientas.confirmar` relee al
ejecutar, así que lo que se ve es lo que se hace. Botones: **Permitir** y **Rechazar**, nada más.
**No existe «Siempre»** (decisión de seguridad: cada acción se aprueba una por una, en el panel y
en Telegram). Permitir vale una sola vez; volver a pulsar no repite la acción.

En Telegram la misma tarjeta llega como texto («Necesito tu permiso: … Detalle exacto de lo que voy
a hacer: • Nombre: …») con botones *inline* **Permitir / Rechazar**; solo el dueño del chat
vinculado puede pulsarlos.

### Pastillas de estado (cabecera del chat)

`brian.conversacion.estado_panel()` devuelve las pastillas que **ese usuario** puede ver; el
servidor decide según el rol (cada bloque pregunta `has_access` y lee sin sudo, con sus reglas de
registro; el único sudo cuenta las claves de API del propio usuario):

| Pastilla | Quién la ve | Qué dice |
|---|---|---|
| Telegram | todos | «Telegram conectado» (tono ok) o «Telegram sin vincular» |
| MCP | todos | «MCP activo» si tiene una clave de API vigente (global o alcance `brian`); si no, «MCP sin clave» |
| Importaciones | quien ve `brian.importacion` (vendedoras las suyas, Gerencia todas) | «N importación(es) por aplicar» (tono aviso; solo si hay borradores) |
| Consumo de IA | administradores (quien lee `brian.uso`) | «IA este mes: N llamadas · $X.XX»; sin tarifa registrada, solo tokens (nunca un costo inventado) |
| Última actividad | todos | «Última actividad: hoy 14:05» / «ayer…» / fecha, en hora de Panamá |

El panel las carga al abrir, las refresca al terminar cada turno y al volver a la pestaña. Son un
extra: si fallan, el chat sigue igual.

### Estados del avatar (preparado, sin construir)

El panel (`<aside id="o_brian_panel">`) lleva **siempre** una clase `o_brian_avatar_<estado>` y
`data-avatar="<estado>"`, que pone `brian_panel.js` (`ESTADOS_AVATAR`, getter `estadoAvatar`):

| Estado | Cuándo |
|---|---|
| `esperando` | nada en curso, sin pendientes |
| `trabajando` | hay un turno en marcha (pasos en vivo) |
| `te_necesito` | hay una tarjeta Permitir / Rechazar sin responder, o el último mensaje es un error |
| `termine` | acaba de responder (8 s, `TERMINE_MS`, o hasta que la persona vuelve a escribir) |

Las clases existen en `brian_panel.scss` **intencionalmente vacías**: cuando se dibuje el avatar
(ronda posterior) se cuelga de ellas sin tocar el JS, p. ej. `.o_brian_avatar_trabajando
.o_brian_monograma { … }`. Reglas de marca de siempre: plano, sin degradados, sin amarillo sobre
blanco.

## Adjuntos que Brian lee

El tipo se decide por la **firma del archivo**, no por la etiqueta del navegador (que manda
`application/vnd.ms-excel` tanto para un CSV como para un .xls binario):

* **Excel** `.xlsx`/`.xlsm` (openpyxl) y `.xls` (xlrd): por hoja, nombre y tamaño, las filas de
  título como contexto, el encabezado (la fila más llena entre las primeras 10) y la tabla;
  números redondeados a 2 decimales; fórmulas sin valor guardado se marcan; recorte con
  «… N filas más». Avisa cuántas imágenes incrustadas trae cada hoja (el modelo no las ve;
  `proponer_importacion` las usa como foto de su fila). El encabezado del bloque lleva el número
  del adjunto («adjunto 42») para que Brian se lo pase a las herramientas.
* **Word** `.docx` (texto de párrafos y tablas), **PDF** (texto), texto/CSV/JSON/Markdown.
* Protegidos con contraseña o dañados: mensaje amable, la conversación sigue.
* **Fotos**: se ajustan para el modelo (lado mayor ≤ 1568 px, JPEG calidad 85 o PNG si tiene
  transparencia, ≤ 5 MB) sin tocar el adjunto original. Formatos que PIL no abre (p. ej. HEIC)
  reciben un aviso: mándala como JPG o PNG.

## Importar productos desde el Excel de un proveedor

Para el inventario nuevo: se le manda a Brian el Excel del proveedor (chat o Telegram) y se le
pide «carga estos productos». Tres herramientas, mismo catálogo en los tres canales:

| Herramienta | Nivel | Quién | Qué hace |
|---|---|---|---|
| `proponer_importacion(adjunto, hoja?, columna_precio?, modo_itbms?)` | construcción | Vendedora y Gerencia | Lee el Excel y deja un **borrador** `brian.importacion` con la vista previa. No toca productos. |
| `aplicar_importacion(importacion_id)` | **sensible** | Solo Gerencia | Crea y actualiza los productos (la persona confirma con un clic; desde MCP nunca). |
| `deshacer_importacion(importacion_id, motivo)` | **sensible** | Solo Gerencia | Revierte una importación aplicada. |

**Lectura** (`models/lector_importacion.py`, funciones puras):

* Encabezado: la fila (entre las 10 primeras) con más columnas reconocidas; título, proveedor y
  buscador de arriba se ignoran. Roles por el texto del encabezado: Código/SKU/Referencia →
  `default_code`, Descripción/Nombre → `name`, Medidas → `dcasa_medidas` (con la etiqueta del
  encabezado, p. ej. «L × A × Alto: 228 × 223 × 120 cm»; un «Queen» sin números no son medidas),
  Tamaño (o el nombre) → atributo Tamaño, Categoría (o el nombre) → categoría con las reglas de
  `dcasa_catalogo/reglas.py`.
* Precio: la primera columna que dice «precio» (nunca «costo»), o la que se pida con
  `columna_precio` (letra o encabezado). Si hay otras, la vista previa las nombra. Los números
  se redondean a 2 decimales (`259.98999999999998` → 259.99); «$—», texto o vacío = sin precio
  (no se importa); una fórmula sin valor guardado se avisa, no se calcula.
* Filas de totales al pie («TOTAL») no son productos.
* **Fotos incrustadas**: cada imagen flotante (`ws._images`) se asigna a la fila que cubre la
  mayor parte de su alto, calculado con el alto real de cada fila (en el catálogo LTSC-07 dos
  fotos empiezan al final de la fila anterior y se corrigen solas). Una foto que cruza dos filas
  por igual, que cae fuera de la tabla o que comparte fila con otra **no se asigna**: se avisa.
  Se guarda normalizada (lado mayor ≤ 1920 px; JPEG calidad 85, o PNG si tiene transparencia).
  Las imágenes *dentro* de celdas de Excel 365 todavía no se leen (se avisa).

**Decisión por fila** (crear / actualizar / omitir):

* Se empareja por `default_code` exacto, sin espacios y sin distinguir mayúsculas (también
  contra archivados).
* Omite (con motivo): sin código, **código repetido en el archivo** (todas sus filas, hasta que
  se corrija), sin precio o precio ≤ 0, varios productos con ese código en Odoo, producto
  archivado, código de una variante de un producto con varios tamaños, o sin cambios.
* Crear: con las reglas del catálogo (`valores_producto_nuevo` de `dcasa_catalogo`):
  inventariable, existencias sin confirmar, ITBMS 7 % que se suma, categoría interna y de la
  tienda, tamaño único como atributo, foto y medidas. **Nace sin publicar** (se publica con
  `publicar_producto_web`, como `crear_producto`).
* Actualizar: **solo el precio**; medidas y foto se llenan si el producto no tenía. Nombre,
  categoría, publicación y lo demás no se tocan. Cada línea guarda el *antes* y el *después*.
* `modo_itbms` es obligatorio en el borrador: `mas_itbms` (D'CASA, por defecto: `list_price` =
  precio del Excel tal cual, la web muestra «+ ITBMS») o `incluido` (se divide entre 1 + tasa).
* Avisos de la vista previa: códigos repetidos, sin precio, cambios de precio de más del 30 %
  (también en la tarjeta de confirmación), productos nuevos sin foto, fotos sin asignar, otras
  columnas de precio, encabezado de precio que menciona el ITBMS.

**Aplicar** corre como el usuario (sin sudo), línea por línea con savepoint: una línea con error
queda marcada y las demás siguen. Si un código apareció entre la vista previa y la confirmación,
esa línea da error (no duplica). Una importación se aplica una sola vez.

**Deshacer**: lo creado se **borra** si nadie lo usó (ni ventas, ni inventario, ni facturas, ni
compras, ni está publicado); si no, se **archiva**. Lo actualizado vuelve a su valor anterior
**solo si sigue como lo dejó la importación** (un precio cambiado a mano después se respeta y se
reporta).

**Registro**: `brian.importacion` y `brian.importacion.linea` (Brian › Importaciones de
productos). ACL de solo lectura: nadie los escribe por RPC; los escribe el sistema después de
comprobar permisos. Cada vendedora ve las suyas; Gerencia, todas. No agregan métodos públicos
(superficie RPC sin cambios).

## Configuración

| Variable | Ejemplo |
|---|---|
| `BRIAN_PROVEEDOR` | `anthropic` · `openai` · `xai` · `groq` · `openrouter` · `ollama` |
| `BRIAN_MODELO` | Anthropic por defecto `claude-sonnet-5-5` (económico: `claude-haiku-4-5`); en los demás proveedores es obligatorio, p. ej. `gpt-4o-mini`, `llama-3.3-70b-versatile` |
| `BRIAN_HERRAMIENTAS_MAX` | opcional: cuántas herramientas ofrecer por mensaje (0 = automático) |
| `BRIAN_ESFUERZO` | opcional (Anthropic): `low`, `medium`, `high`, `xhigh`, `max`. Vacío = el del modelo. Haiku 4.5 no lo recibe |
| `BRIAN_CACHE` | caché de prompts de Anthropic, activa por defecto; `0` la apaga |
| `BRIAN_API_KEY` | secreto |
| `BRIAN_BASE_URL` | opcional (OpenAI-compatible) |
| `TELEGRAM_BOT_TOKEN` | secreto |

(Cada variable también se puede poner como parámetro del sistema `dcasa_brian.<clave>`:
`esfuerzo`, `cache`, …)

## Costo y consumo

* **Caché de prompts** (Anthropic): marca de caché en la última herramienta, en la parte fija
  del sistema (`brian.conversacion._sistema_fijo`: sin fecha, persona ni pantalla) y en el último
  mensaje. En el bucle, cada paso relee lo anterior a ~10 % del precio.
* **`brian.uso`**: una fila por llamada al modelo (persona, canal, modelo, tokens de entrada,
  salida, leídos y escritos en caché). Solo lectura para administradores (Brian › Consumo de IA);
  la escribe el sistema; sobrevive al borrado de la conversación.
* `consumo_de_brian(periodo)` (administradores): llamadas y tokens por modelo y persona, % leído
  de caché y costo estimado con la tarifa pública (`models/uso.py`, `PRECIOS`); un modelo sin
  tarifa se reporta «sin tarifa registrada».
* Un turno no pasa de 150 s (`MAX_SEGUNDOS_TURNO`): Brian se detiene y lo dice. Si el proveedor
  corta la respuesta por largo, Brian lo avisa.

## Herramientas del día a día (ronda 6)

| Herramienta | Nivel | Quién |
|---|---|---|
| `sugerir_reabastecimiento` — vendido en N días, hay, en camino, comprometido, cuánto pedir para cubrir N días, proveedor y costo | lectura | Inventario |
| `crear_pedido_compra(proveedor, lineas)` — solicitud de compra en borrador | construcción | Compras |
| `buscar_compras` — borradores, confirmadas, por recibir | lectura | Compras |
| `que_reponer(proveedor?, meses?, reserva?)` — lo mismo que Compras › Reponer: por producto, vendido en los últimos N meses (de fábrica 5; facturas menos notas de crédito), se vende al mes, disponible hoy (en bodega − lo vendido por entregar), viene en camino, alcanza para, tarda en llegar, pedir y `pedir_ya`, de más urgente a menos. Sin el tiempo de llegada del proveedor no calcula cuánto pedir (lo dice) | lectura | Gerencia y administradores |
| `poner_tiempo_llegada(proveedor, dias? / meses?)` — guarda cuánto tarda en llegar un proveedor (1 día a 24 meses; un mes = 30 días) en todos sus precios de proveedor; queda anotado en su ficha. Nunca lo inventa: lo pregunta | construcción | Gerencia y administradores |
| `pendientes_de_hoy` — entregas, cotizaciones dormidas, compras por recibir, vencidas, publicados agotados, acciones por confirmar | lectura | Interno |
| `entregas_por_despachar(como?, estado?, limite?)` — las del panel de Bodega: cuántas para envío, para retirar en la tienda y sin definir; listas para salir y esperando producto; las más antiguas con cliente, pedido, fecha, productos y «con abono: falta una parte» (sin montos ni precios); solo pedidos con pago o abono; botón para abrir el panel (módulo `dcasa_barras`) | lectura | Inventario |
| `productos_incompletos` — sin foto, precio, categoría, medidas o código | lectura | Interno |
| `publicar_productos_en_bloque` — una tarjeta con cuáles; al publicar se saltan los sin foto o sin precio | sensible | Gerencia de ventas |
| `ajustar_existencias_en_bloque(cantidad, productos? / categoria? / todos?, almacen?)` — deja la misma cantidad en varios productos a la vez (lo normal: en cero). La tarjeta dice cuántos y cuáles; `todos` solo sirve con cantidad 0 y toma los que hoy tienen existencias en el almacén; hasta 1,000 por vez | sensible | Gerencia de inventario |
| `actualizar_productos_en_bloque(campo, productos? / categoria?, valor? / porcentaje?)` — cambia varios productos a la vez: `precio` (valor fijo o porcentaje, sin ITBMS), `categoria` o `vendible`; la tarjeta muestra el antes y el después de cada uno; hasta 200 por vez | sensible | Gerencia de ventas |
| `consumo_de_brian` | lectura | Administrador |
| `oportunidades_abiertas(temperatura?, para_hoy?, limite?)` — las del CRM que nacieron de una conversación, de la más caliente a la más fría: etapa, qué pidió, para cuándo, zona, si esperan respuesta o tienen cotización; `para_hoy` = tibias y calientes sin mensaje de una vendedora en 24 h (módulo `dcasa_conversaciones`) | lectura | Ventas |
| `resumen_del_crm` — abiertas por temperatura y por etapa, las que esperan respuesta, con cotización enviada, en manos de una persona y lo ganado y archivado en 30 días | lectura | Ventas |

| `buscar_en_guia(consulta)` — busca en la Guía del negocio (módulo `dcasa_guia`, [GUIA.md](GUIA.md)) qué pantalla sirve para lo que la persona quiere hacer (declaración de renta, ITBMS, cerrar el mes, planilla…): qué logra, dónde queda en el menú, los pasos y la nota; solo lo que quien pregunta puede abrir | lectura | Interno |

**Ventas, ITBMS y ganancia (2026-10-16).** `resumen_ventas` y `reporte_del_dia` dan las ventas **sin ITBMS** (la cifra
principal), con el ITBMS y el total con ITBMS aparte; lo cobrado va con ITBMS. Solo para Gerencia y administradores
agregan la **ganancia** (venta menos costo, sin ITBMS); a la Vendedora nunca le llega el costo ni la ganancia. Si hay
ventas con productos sin costo cargado, lo avisan en vez de inventar la ganancia. Son las mismas cifras del Inicio.

**Facturado, Con abonos o Completadas, por vendedora, y comparar (2026-10-17).** Para Gerencia, Brian cuenta las ventas
como su Inicio, **sobre las facturas publicadas** (como Contabilidad) y con las mismas palabras del interruptor
([OPERACION.md](OPERACION.md), «Facturado, Con abonos o Completadas, y Comparar»):

| Herramienta | Qué hace | Nivel | Quién |
|---|---|---|---|
| `resumen_ventas(periodo?, desde?, hasta?, base?, vendedora?)` | Lo de siempre y, para Gerencia, `base` = `facturado` (por defecto: todas las facturas publicadas, por su fecha, igual que Contabilidad; las notas de crédito restan; agrega `de_un_pedido`, «N de M salieron de un pedido de una vendedora»), `con_abonos` (con al menos un abono, por su valor total; agrega `falta_por_cobrar_con_itbms`) o `completadas` (pagadas al 100 %, el día del último pago), y `vendedora` (un nombre o «sin vendedora»; una factura es de la vendedora de su pedido o, sin pedido, de su «Vendedor»). La respuesta dice qué cuenta (`cuenta`) y cuántas notas de crédito restaron (`notas_de_credito`). Trae el ticket promedio (`ticket_promedio_sin_itbms`, «—» sin ventas) y, para Gerencia, `unidades_por_tipo` y `unidades_total`, los mismos del Inicio (categoría de primer nivel; «Otros» pasados 8 tipos; las notas de crédito restan). Quien vende sin controlar ve solo lo suyo, sus pedidos facturados por completo; si pide otra vendedora, se le niega | lectura | Ventas |
| `comparar_ventas(comparacion, a?, b?, base?, vendedora?)` | Las cifras del bloque **Comparar**: `ayer`, `dia_mes_pasado`, `semana_pasada`, `mes_a_la_fecha`, `mes` (contra el mes completo que diga `b`: «septiembre», «09/2026» o «2026-09»; responde «Llevas 58 % de septiembre») o `rango` (`a` = «01/10/2026-07/10/2026»; `b` = dónde empieza B, del mismo largo, o B entero si es de otro largo, y entonces el % va por día). Filas: ventas, ganancia, margen (en puntos), número de ventas, ticket promedio, falta por cobrar (con abonos) y cobrado, con su cambio («▲ 27.6 %», «▼ 5.4 pts», «—» sin base). Si A termina hoy, dice hasta qué hora se cortó. `vendedora=por vendedora` agrega una fila por vendedora (5 parámetros: el contrato de los modelos pequeños) | lectura | Gerencia |

**Por día y movimientos de inventario (2026-10-22).** Las mismas cuentas de *Por día* y de *Inventario › Movimientos*
([OPERACION.md](OPERACION.md), «Por día, Estadísticas y Movimientos»):

| Herramienta | Qué hace | Nivel | Quién |
|---|---|---|---|
| `ventas_por_dia(dia?, mes?, base?, vendedora?)` | Con `dia` («hoy», «ayer», «el martes» = el último martes, hoy incluido; «el martes pasado» = antes de hoy; o «20/10/2026»): el total de ese día sin ITBMS (ITBMS y total aparte) y cada factura o pedido con cliente, vendedora, monto y estado. Sin `dia`: cada día del mes con ventas (`mes` = «este mes», «mes pasado», «septiembre», «09/2026»), el total, el ticket promedio, el mejor día y la comparación con el mes anterior (la misma de la pantalla). `base`: `facturado` (por defecto), `confirmado` (lo vendido: pedidos confirmados, el día que se confirmaron), `con_abonos` o `completadas` (pagadas por completo, el día que se terminó de pagar) | lectura | Gerencia |
| `movimientos_de_producto(producto?, desde?, hasta?, tipo?, limite?)` | La historia de un producto (nombre, código o código de barras) en palabras: «Entró por la compra… de…», «Salió por la venta… a…», ajustes, devoluciones y traslados, con la cantidad (+/−), lo que quedó (solo si la historia cuadra; si no, lo avisa), quién y cuándo, y lo que hay hoy. Sin producto, los últimos movimientos de todos. `tipo`: compra, venta, devolucion, ajuste, traslado u otro | lectura | Gerencia de inventario y administradores |

Ejemplos: «¿cuánto se facturó el martes?» → `ventas_por_dia(dia=el martes)`; «ventas por día de este mes» →
`ventas_por_dia()`; «¿qué movimientos tuvo el SOF-001?» → `movimientos_de_producto(producto=SOF-001)`.

`reporte_del_dia` le da a Gerencia las ventas de hoy como su Inicio (`ventas_de_hoy`, en «Facturado», con
`de_un_pedido`) en lugar de «Vendido hoy», que sigue siendo la cifra de la vendedora; lo más vendido de los 30 días es
también el del Inicio de Gerencia («Facturado»). Ejemplos: «¿cómo vamos contra septiembre?» →
`comparar_ventas(comparacion=mes, b=septiembre)`; «¿cómo va Ana este mes?» →
`comparar_ventas(comparacion=mes_a_la_fecha, vendedora=Ana)`.

Brian **solo lee** el CRM: cerrar o ganar oportunidades no está hecho a propósito (docs/CRM_AUTOMATICO.md, «Lo que NO se hace»).

**Combos cama + colchón que se arman en la venta (2026-10-22, `herramientas_combos.py`).** Las mismas reglas del panel
«Armar combo» de la cotización ([OPERACION.md](OPERACION.md), «Combos cama + colchón»): el colchón va a su **precio en
combo** (el que puso Gerencia, por medida) solo si en la misma venta va una cama de su medida; sin precio en combo, a
precio normal. Brian corre como quien le habla (tope de descuento y «solo lo suyo» incluidos).

| Herramienta | Qué hace | Nivel | Quién |
|---|---|---|---|
| `colchones_para_cama(cama, todos?)` | Los colchones de la medida de la cama, con existencia (`todos`: también los agotados): precio normal, precio en combo, ahorro y disponibles. Una cama sin medida lo dice | lectura | Ventas |
| `armar_combo(cama, colchon, venta? / cliente?, cantidad?)` | Agrega la cama y el colchón de su misma medida a una cotización (o a una nueva para `cliente`); devuelve el resumen con `el_cliente_ahorra_sin_itbms` | construcción | Ventas |
| `cambiar_combo(venta, cama_nueva? / colchon_nuevo?, cama_actual?)` | Cambia la cama o el colchón del combo (con varios combos, `cama_actual` dice cuál); el precio se vuelve a calcular | construcción | Ventas |
| `poner_precio_en_combo(colchon, precio)` | El precio en combo de un colchón en una medida (sin ITBMS, menor que el normal; 0 lo quita) | construcción | Gerencia |

`crear_cotizacion` con una cama y un colchón de la misma medida ya da el precio en combo, y el resumen de cualquier
cotización (`ver_venta`, `crear_cotizacion`…) marca las líneas que van en combo (`combo`: «Combo · ahorras $40.00»).

`crear_cotizacion` y `agregar_linea_cotizacion` aceptan `lineas` («SOF-001 x 2; MES-003 x 1 @ 99»;
máx. 30). Los modelos pequeños pueden mandar números y sí/no como texto: el registro los convierte
(`registro.coercer`), y un parámetro mal puesto responde con la lista de los válidos.

## Marketing y fotos (2026-10-22, módulo `dcasa_marketing`)

Las mismas cifras de la app **Marketing** ([MARKETING.md](MARKETING.md)); nada lo calcula el modelo de IA.

| Herramienta | Qué hace | Nivel | Quién |
|---|---|---|---|
| `movimiento_de_productos(periodo?, que?, categoria?, limite?)` | `periodo` = `semana` (7 días corridos, por defecto), `15_dias` o `mes` (30 días); `que` = `mas_movimiento` (lo vendido o entregado; una venta facturada y entregada cuenta una vez), `quietos` (con stock y sin ventas ni entregas; primero los que nunca se vendieron, con la última venta y los días sin vender), `mas_vendidos` (unidades facturadas, las notas de crédito restan, la base del Inicio) o `todo`; `categoria` = el tipo (p. ej. «Salas»). Responde cómo se cuenta (`como_se_cuenta`) | lectura | Gerencia, administradores y el rol Marketing |
| `fotos_que_faltan(estado?, texto?, categoria?, limite?)` | Productos a la venta sin foto (`sin_foto`), con una sola (`una_foto`) o los dos (`faltan`, por defecto); con cuántas tiene cada uno, los conteos y dónde subirlas (Marketing › Fotos o tocando la foto del producto) | lectura | Interno |

Ejemplos: «¿qué productos están más quietos esta semana?» → `movimiento_de_productos(que=quietos)`; «¿qué se movió más
este mes en Salas?» → `movimiento_de_productos(periodo=mes, que=mas_movimiento, categoria=Salas)`; «¿a qué colchones les
faltan fotos?» → `fotos_que_faltan(categoria=Colchones)`. Brian no sube ni cambia fotos (eso se hace en la pantalla).

## Roles y «Cada vendedora ve solo sus documentos» (2026-10-17)

* **Roles** de `listar_usuarios`, `cambiar_rol_usuario` y `crear_usuario` (`herramientas_usuarios.py`, `ROLES`):
  `vendedor` = «D'CASA / Vendedora», `cajero` = «D'CASA / Caja» (factura y cobra lo de toda la tienda), `gerencia` =
  «D'CASA / Gerencia» (solo la da un administrador del sistema, igual que `administrador`), `contador` y
  `administrador`. Un cambio de rol quita antes los tres roles D'CASA y «Ventas: todos los documentos»: pasar de Caja a
  Vendedora no deja a la persona viendo lo de sus compañeras. Antes Brian llamaba «Cajero/a» a la Vendedora y a Gerencia.
* **Brian corre como quien le habla**: con el interruptor encendido, a la Vendedora no le encuentra la venta, la
  factura de otra (`ver_venta` y `ver_factura` responden que no la encuentran: las reglas filtran). Las herramientas que dan
  cifras de facturas o cotizaciones (`clientes_que_deben`, la deuda de un cliente, `facturas_pendientes`,
  `pendientes_de_hoy`) agregan la clave **`alcance`** («solo tus facturas y las que no tienen vendedora») para que no
  presente una cifra parcial como si fuera la de toda la tienda. A Caja, contabilidad y Gerencia no se les agrega.
* **`cambiar_restriccion_vendedoras(encender)`** (sensible, Gerencia o administrador): enciende o apaga «Cada vendedora
  ve solo sus documentos» (lo mismo que *Ventas › Configuración › Permisos de las vendedoras*). `listar_usuarios` dice
  cómo está (`cada_vendedora_ve_solo_lo_suyo`). Ejemplo: «que las vendedoras vuelvan a ver todo».

## Reglas contables de la gerencia (2026-10-17)

Brian corre como quien le habla, así que las reglas del servidor ([PERMISOS.md](PERMISOS.md), «Reglas contables de la
gerencia») le valen igual; además:

* **`registrar_pago`** solo sale a quien cobra: Caja, Gerencia, contabilidad o administrador. `grupos` acepta ahora un
  elemento «alguno de» (una tupla dentro de la tupla: `('account.group_account_invoice', (Caja, contador, …))`). A la
  Vendedora no se le ofrece; si de todos modos llega a la herramienta, responde «Los cobros los registra Caja…». Con
  el interruptor «ver solo lo suyo» apagado, tampoco.
* El **primer abono** menor a la mitad del total: `registrar_pago` usa el asistente «Pagar», así que a Caja y a
  contabilidad les contesta «El primer abono debe ser de al menos la mitad: $X. Si es menos, lo registra Gerencia.»;
  Gerencia sí lo registra (queda una nota en la factura). Los abonos siguientes y el pago completo son libres.
* `forma_pago` acepta **Tafi** y **Crediviva** (diarios «Tafi (financiamiento)» y «Crediviva (financiamiento)»).
* **El vencimiento del abono** sale de `_dcasa_estado_abono` (30 días continuos desde el primer abono): `ver_factura` y
  `facturas_pendientes` agregan, en una factura de cliente en abono, `abono` = `{inicio, pagado, saldo, vence,
  vencido}`. El `vence` de siempre sigue siendo el de la condición de pago de la factura.
* **El prompt**: a quien no cobra, Brian sabe que «los cobros los registra Caja (o Gerencia)»; a quien no es Gerencia,
  que anular, pasar a borrador, notas de crédito y devolver dinero son solo de Gerencia. Brian no tiene herramientas
  para anular, pasar a borrador ni hacer notas de crédito (sigue siendo de una persona).

## Bodega, nómina y el ZIP de comprobantes (2026-10-22)

Archivo `models/herramientas_bodega_nomina.py` (usan modelos de `dcasa_existencias`, `dcasa_nomina` y
`dcasa_contabilidad`; si uno no está instalado, la herramienta lo dice). Pruebas: `tests/test_bodega_nomina_brian.py`.

| Herramienta | Nivel | Quién | Qué hace |
|---|---|---|---|
| `resumen_de_mermas` | lectura | gerente de Inventario (Gerencia) | Mermas del mes por código, contra lo comprado y el tope del 0.5 % |
| `registrar_merma` | sensible | gerente de Inventario | Da de baja una merma, daño, muestra o regalo (pide «qué pasó») |
| `bitacora_de_bodega` | lectura | gerente de Inventario | Últimos ajustes: antes → después, motivo y quién |
| `adelantos_y_prestamos` | lectura | Administra la nómina | Adelantos con su saldo y cuota por quincena |
| `registrar_adelanto` | construcción | Administra la nómina | Lo deja «por autorizar» (lo autoriza Gerencia en la pantalla) |
| `enviar_comprobantes_de_pago` | sensible | Administra la nómina | Manda los comprobantes de una planilla confirmada (respeta el interruptor de correos) |
| `preparar_zip_de_comprobantes` | construcción | contabilidad | Prepara el ZIP de un año o un rango; avisa cuando está listo |

Además, **`ajustar_existencias` y `ajustar_existencias_en_bloque` piden ahora el `motivo`** (obligatorio): queda en la
bitácora de bodega con origen «Brian». La tarjeta de confirmación del bloque lo muestra.

## Para cada función nueva

Toda función nueva de la plataforma debe poder usarla Brian (ver la plantilla de PR):
registrar su herramienta con nivel, respetar la política y llevar test.

## Conectarse

### MCP (Claude Desktop, Claude Code, otros clientes MCP)

Endpoint: `POST https://dcasapty.com/brian/mcp` — MCP revisión **2025-06-18**, transporte
*Streamable HTTP*, respuestas `application/json` (sin SSE; `GET`/`DELETE` → 405). Un mensaje
JSON-RPC por petición: los lotes se rechazan (la 2025-06-18 los eliminó).

1. **Crear la clave de API en Odoo** (con el usuario que va a usar Brian; todo corre con sus
   permisos): avatar → *Mis preferencias* → pestaña *Seguridad* → *Nueva clave de API* →
   nombre (p. ej. «Claude Desktop de Ana») y vencimiento. Copiarla: Odoo no la vuelve a mostrar.
   Sirve una clave global o una con alcance `brian`.
2. **Configurar el cliente** con la URL y el encabezado `Authorization: Bearer <clave>`.
   Ejemplo (cliente con soporte HTTP remoto):

   ```json
   {
     "mcpServers": {
       "brian-dcasa": {
         "type": "http",
         "url": "https://dcasapty.com/brian/mcp",
         "headers": { "Authorization": "Bearer ${BRIAN_ODOO_API_KEY}" }
       }
     }
   }
   ```

   En Claude Code: `claude mcp add --transport http brian-dcasa https://dcasapty.com/brian/mcp
   --header "Authorization: Bearer $BRIAN_ODOO_API_KEY"`. La clave va en una variable del
   equipo, nunca en un archivo del repositorio.
3. `tools/list` devuelve las herramientas que ese usuario puede usar, con anotaciones:
   `readOnlyHint` (lectura), `destructiveHint` (sensible), `openWorldHint: false`.

Reglas del canal MCP:

* Sin clave válida → 401 con `WWW-Authenticate: Bearer`. Clave vencida o revocada = sin acceso.
* **Las herramientas sensibles nunca se ejecutan desde MCP**: la llamada responde
  `isError: true` con el resumen y el `accion_id`, y la acción queda «por confirmar». La
  confirma una persona en el panel o en Telegram (si el usuario tiene el chat vinculado, le
  llegan al instante el detalle exacto y los botones Permitir / Rechazar). `rechazar_accion`
  siempre existe.
* Solo si un administrador pone el parámetro del sistema `dcasa_brian.mcp_permite_confirmar`
  en `True` aparece la herramienta `confirmar_accion` (marcada `destructiveHint`), pensada para
  clientes que piden aprobación humana en cada llamada. Por defecto está apagado.
* Límites: 1 MB por mensaje, 120 peticiones por minuto por usuario, 20 intentos fallidos por
  minuto por IP, más el límite de acciones por minuto de la política.
* Si llega `Origin` (navegador), debe ser el de `web.base.url` o uno de
  `dcasa_brian.mcp_origenes` (separados por coma); si no, 403 (protección DNS rebinding).

### Telegram

1. **Crear el bot**: en Telegram, hablar con [@BotFather](https://t.me/BotFather) → `/newbot`
   → nombre («Brian D'CASA») y usuario (terminado en `bot`). Copiar el token. Recomendado:
   `/setjoingroups` → *Disable* (Brian solo responde en chats privados).
2. **Guardar los secretos** (GitHub → *Settings → Secrets and variables → Actions*, environment
   `production`; el despliegue los sube al Worker con `wrangler secret bulk`):
   * `TELEGRAM_BOT_TOKEN` — el token de @BotFather.
   * `BRIAN_TELEGRAM_SECRETO` — texto aleatorio largo (solo `A-Z a-z 0-9 _ -`), p. ej.
     `openssl rand -hex 32`. Va en la URL del webhook y en el encabezado
     `X-Telegram-Bot-Api-Secret-Token`; sin él, el webhook responde 404.
3. **Registrar el webhook**: con `web.base.url` = `https://dcasapty.com`, un administrador va a
   *Brian → Telegram* y pulsa **Registrar webhook** (llama a `setWebhook` con
   `https://dcasapty.com/brian/telegram/<secreto>`; guarda el @usuario del bot para los mensajes).
4. **Vincular** (cada persona, una vez): *Mis preferencias* → **Vincular Telegram** (o *Brian →
   Telegram* → *Vincular mi Telegram*). Aparece un código de 6 dígitos que vence en 10 minutos y
   sirve una sola vez; enviarle al bot `/vincular 123456`. Desde ese chat Brian trabaja con los
   permisos de esa persona.

Comandos del bot: `/ayuda`, `/nuevo` (conversación nueva), `/desvincular`, `/vincular CÓDIGO`.
Se pueden mandar fotos y documentos (hasta 10 MB): se guardan como adjuntos de la conversación.
Las acciones sensibles llegan con el detalle exacto y botones **Permitir / Rechazar** (sin
«Siempre»); solo el dueño del chat vinculado puede pulsarlos. Un chat no vinculado solo recibe las instrucciones para vincularse.
Para cortar el acceso: `/desvincular` en el chat, o *Brian → Telegram* → *Desvincular*.

#### Conectar el Telegram de la gerencia (paso a paso, sin correo)

Odoo **no tiene servidor de correo saliente** (`docs/PLAN.md`): ningún paso depende de un correo. **Brian tiene su propio bot**, distinto
del bot de Juan (el de los clientes): un bot solo tiene un destino y usar el de Juan le quitaría la conexión.

1. **Crear el bot**: en Telegram, @BotFather › `/newbot` › nombre `Brian D'CASA` y un usuario que termine en `bot`. Copiar el
   token (nunca por el chat ni en el repositorio).
2. **El ID del jefe** (un número, no es secreto pero es personal): él le escribe `/miid` al bot de Juan (o al de Brian, que también lo
   dice mientras no haya lista) y recibe «Tu chat id es: 123456789». Es el mismo número en cualquier bot.
3. **Secretos y variable en Cloudflare**: Workers y Pages › `dcasa` › Settings › Variables and Secrets. **Secret** `TELEGRAM_BOT_TOKEN`
   (el token), **Secret** `BRIAN_TELEGRAM_SECRETO` (40 letras y números al azar) y **Text** `BRIAN_TELEGRAM_CHATS` con el ID del jefe
   (varios: separados por coma). Deploy. (Los despliegues no tocan lo que se pone en el panel.)
4. **Que Odoo los recoja**: el contenedor los lee al arrancar: entran con el próximo despliegue o con un reinicio.
5. **Registrar el bot** (administrador): Brian › Telegram › **Registrar webhook**. Confirma y muestra el @ del bot. Si dice «Falta
   TELEGRAM_BOT_TOKEN», el contenedor todavía no recogió el secreto. Si sale **ATENCIÓN: no hay lista de chats permitidos**, falta
   `BRIAN_TELEGRAM_CHATS`: hasta que se ponga, cualquiera que encuentre el bot recibe las instrucciones para vincularse.
6. **El usuario del jefe**: Ajustes › Usuarios › Nuevo (rol Gerencia; además Administrador si va a recibir los avisos de operación y de
   inicios de sesión). La clave se la pone un administrador: usuario › Acciones › **Cambiar contraseña** (no llega invitación por
   correo). Si es administrador, al entrar enrola el código de la app (Google Authenticator), que tampoco usa correo.
7. **Él pide su código**, con su propia sesión: Brian › Telegram › **Vincular mi Telegram** (o Mis preferencias › Vincular Telegram).
   Sale un aviso con un código de 6 números (vence en 10 min, sirve una vez). El botón solo vale para quien tiene la sesión abierta.
8. **En su Telegram**, en el bot de Brian: `/vincular 123456`. Brian contesta «Listo, <nombre>: este chat quedó vinculado a tu usuario».
9. **Aviso de «el contenedor se cayó»** (Odoo está apagado y avisa el Worker): en Cloudflare, como **Text**,
   `DCASA_ALERTA_TELEGRAM_CHAT` con el mismo ID. No va en el repositorio: es un dato de una persona.

**La lista de chats permitidos** (`BRIAN_TELEGRAM_CHATS`, o el parámetro `dcasa_brian.telegram_chats` en Ajustes › Técnico):
con ella puesta Brian **solo** atiende y solo le escribe a esos chats. De cualquier otro no contesta nada (tampoco las instrucciones
para vincularse ni `/miid`), no deja vincularse aunque traiga un código válido, ignora sus botones, y los avisos (inicios de sesión,
disco, caídas) solo salen hacia chats de la lista. Un valor sin ningún número (un error al escribirlo) cuenta como lista vacía:
nadie. **Sin la variable todo sigue como antes**: por eso el paso 5 lo advierte. Si más adelante vendedoras responden a clientes por
Telegram (la consola del equipo usa este mismo bot), sus IDs se agregan a la lista. Lo que aún **no** se filtra en el borde: un
mensaje de un chat no permitido todavía despierta el contenedor (Odoo lo ignora sin contestar).

Lo que Brian avisa hoy a los administradores vinculados: inicios de sesión del personal, disco/memoria/base al límite, caídas del
contenedor y las acciones que esperan permiso (con botones Permitir / Rechazar). Un resumen de ventas o de lo vencido por Telegram
**no existe todavía**.

## Correo

Con el correo a clientes encendido ([CORREO.md](CORREO.md)), Brian también manda documentos por correo, con la marca
D'CASA y el PDF:

| Herramienta | Nivel | Quién | Qué hace |
|---|---|---|---|
| `enviar_factura_por_correo` | construcción | Facturación | Encola la factura publicada de un cliente; sale con su PDF nuevo (si todavía debe algo, como abono: lo pagado, lo que falta y hasta cuándo) |
| `enviar_cotizacion_por_correo` | construcción | Ventas | Manda la cotización (borrador o enviada) con su PDF; si estaba en borrador, pasa a «Enviada». No la confirma |

Si los correos están apagados, o el cliente no tiene un correo bien escrito, Brian lo dice con las mismas palabras que la
pantalla («… no tiene correo. Escríbelo en su ficha o envíasela por WhatsApp.»). Registrar un pago con `registrar_pago`
ya manda la factura sola: no hace falta pedírselo aparte.
