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
  observar) con límite de pasos y de tokens.
* **`herramientas_*.py`** — las capacidades, por área.

## Niveles de permiso

| Nivel | Ejemplos | Comportamiento |
|---|---|---|
| lectura | reporte del día, buscar productos, balance, clientes que deben | Directo |
| construcción | crear producto, cliente, cotización, factura en borrador; editar precio; mover stock | Directo, auditado |
| sensible | confirmar una venta, publicar una factura, registrar un pago, cambiar el rol de un usuario, archivar | Brian propone → el humano confirma con un clic |
| prohibido | ver abajo | No existe herramienta para eso |

### Lo que Brian nunca hace

1. Eliminar, archivar o quitarle permisos al administrador, ni a sí mismo (el usuario con quien conversa).
2. Modificar facturas publicadas o pagadas, asientos publicados ni conciliaciones: eso se corrige con notas de crédito o asientos contrarios, por una persona.
3. Borrar (unlink) registros contables, del libro de puntos (`dcasa.movimiento`) o del registro de acciones de Brian.
4. Tocar el programa Socios fuera de sus reglas (cifras solo de `puntos.json`; el libro no se edita).
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
  (defensa contra inyección de prompts): va marcado como tal al modelo.
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
| `BRIAN_API_KEY` | secreto |
| `BRIAN_BASE_URL` | opcional (OpenAI-compatible) |
| `TELEGRAM_BOT_TOKEN` | secreto |

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
  llegan al instante los botones Confirmar / Cancelar). `rechazar_accion` siempre existe.
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
Las acciones sensibles llegan con botones **Confirmar / Cancelar**; solo el dueño del chat
vinculado puede pulsarlos. Un chat no vinculado solo recibe las instrucciones para vincularse.
Para cortar el acceso: `/desvincular` en el chat, o *Brian → Telegram* → *Desvincular*.
