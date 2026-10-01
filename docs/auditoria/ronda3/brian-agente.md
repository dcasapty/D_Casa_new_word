# Ronda 3 · `r3-brian-agente` — Brian nativo en Cloudflare con Meta como proveedor

> Informe incremental (se va completando). Fecha: 2026-10-01.

## 0. Resumen ejecutivo
(pendiente)

## 1. Cómo se probó a Brian con Meta y cómo conectarlo hoy

### 1.1 Qué dice la evidencia (verificado)

| Hecho | Evidencia |
|---|---|
| No existe proveedor `meta` en el código; un `BRIAN_PROVEEDOR=meta` deja `tipo=None` y Brian dice «falta un proveedor válido». | `addons/dcasa_brian/models/proveedores.py:59-76` (tabla), `:368-370` (`configuracion`), `:398-399` (`estado`) |
| Nunca existió: `git log -p -S meta` sobre `proveedores.py`, `.github/` y `docs/BRIAN.md` no da ninguna línea con Meta/Llama/Muse (solo 2 commits tocan `proveedores.py`: `cff4119`, `2c76488`). | historia de git |
| La única ruta «desde GitHub Actions» con Brian y clave de IA es el workflow **Previsualización**: fuerza `-e BRIAN_PROVEEDOR=anthropic -e BRIAN_API_KEY="$BRIAN_CLAVE"`, con `BRIAN_CLAVE = secrets.BRIAN_API_KEY_PRUEBAS \|\| secrets.BRIAN_API_KEY`, y solo si existe `PREVIEW_ADMIN_PASSWORD`. | `.github/workflows/preview.yml:86-93` |
| El despliegue a Cloudflare (`ci.yml`) sí pasa `BRIAN_PROVEEDOR/MODELO/BASE_URL` como variables del repositorio, pero **la cuenta de Cloudflare tiene 0 Workers** (inventario del coordinador): nunca se desplegó, así que ahí no se probó. | `.github/workflows/ci.yml:187-200`; BITACORA «Inventario real de la cuenta» |
| La ejecución **#33** de Previsualización (id 36734759699, 2026-09-30 15:10→16:21 UTC, commit `5b7b272`, lanzada a mano por `vivimahechagarcia05-spec`, 60 min en línea) es la única con Brian y clave: el log muestra `CLAVE_PRIVADA: ***` y `BRIAN_CLAVE: ***` (ambos secretos existen). Las ejecuciones #29-#31 (con Brian) fallaron o se cancelaron antes de arrancar Odoo. | log del job 109953770510 leído con el MCP de GitHub |
| El log no incluye la salida de Odoo (el paso `docker logs` solo corre si falla), así que **no se puede saber desde aquí qué proveedor respondió**. Los nombres de los secretos tampoco se pueden listar (el proxy devuelve 403 en `/actions/secrets`). | job 109953770510, paso 14 «skipped» |

### 1.2 Las dos explicaciones posibles

1. **El secreto `BRIAN_API_KEY`/`_PRUEBAS` es una clave de Anthropic** y lo que el dueño probó fue Claude Sonnet 5.5 (el defecto, `proveedores.py:57`). Con una clave de Meta y `BRIAN_PROVEEDOR=anthropic`, Anthropic devuelve 401 y Brian muestra «La clave de API de Brian no es válida…» (`proveedores.py:150-151`): no habría «buenas respuestas».
2. **El dueño cambió el proveedor desde el panel** de la vista previa: en Ajustes › Brian, el parámetro `dcasa_brian.proveedor`/`modelo`/`base_url` **gana a la variable de entorno** (`proveedores.py:357-363`, `primero_entorno=False`), mientras que la clave **viene primero del entorno** (`:381`, `primero_entorno=True`). Si eligió «OpenAI (ChatGPT)», escribió la dirección de Meta y el modelo, Brian usó la clave de Meta del secreto con el adaptador Chat Completions. Funciona sin tocar código.

**Hay que preguntarle al dueño cuál fue** (pregunta concreta: «¿en la vista previa entraste a Ajustes › Brian y cambiaste el proveedor, o lo dejaste como venía? ¿La clave que guardaste en GitHub es de Meta o de Anthropic?»). Mientras no responda, ninguna conclusión de calidad sobre Meta debe darse por probada.

### 1.3 Cómo conectarlo HOY sin tocar código

Válido para la vista previa (desde Ajustes, como en la explicación 2) o para producción (variables del repositorio que `ci.yml:187-200` pasa al contenedor):

| Variable / Ajuste | Valor |
|---|---|
| `BRIAN_PROVEEDOR` / Proveedor | `openai` (adaptador Chat Completions, `proveedores.py:238-301`) |
| `BRIAN_BASE_URL` / Dirección del API | URL compatible con OpenAI de Meta **sin** `/chat/completions` (el adaptador la añade, `:251`). Ver §2 para el valor verificado. |
| `BRIAN_MODELO` / Modelo | ID exacto del modelo (ver §2) |
| `BRIAN_API_KEY` (secreto) | la clave de Meta |
| `BRIAN_HERRAMIENTAS_MAX` | `0` (todas) — un ID con `lite`/`mini`/`8b` en el nombre activaría la preselección de 12 (`:79`, `:388-391`) |

Trampas del atajo (por qué «conectarlo así» no es «hacerlo bien»):

- Con `proveedor=openai` el adaptador manda `max_completion_tokens` (`proveedores.py:243`); con cualquier otro nombre manda `max_tokens`. Si el endpoint de Meta no acepta uno de los dos devuelve 400 (ver §2 cuál acepta).
- En la vista previa la variable `BRIAN_PROVEEDOR=anthropic` está fija (`preview.yml:92`): solo se cambia desde Ajustes, y se pierde al terminar la ejecución (base nueva cada vez).
- Una sola `BRIAN_API_KEY` global: no se pueden tener Meta **y** Claude a la vez (ni fallback).
- `uso` se descarta (`conversacion.py:272`): no queda registro de cuánto costó la prueba.
- Las capacidades (visión, tamaño de imagen, PDF) son las de la tabla `openai` (`vision: True`), no las del modelo de Meta.
- La interfaz dice «OpenAI (ChatGPT)» aunque responda Meta: confunde en soporte y auditoría.

### 1.4 Qué falta para hacerlo bien (cambios mínimos en `dcasa_brian`, para el equipo de desarrollo)

1. Entrada `'meta'` en `PROVEEDORES` con `tipo: 'openai'`, `base_url` verificada, modelo por defecto y `vision: True`; `max_tokens`/`max_completion_tokens` según §2.
2. Claves por proveedor (`BRIAN_API_KEY_META`, `BRIAN_API_KEY_ANTHROPIC`…) para permitir ruteo y respaldo.
3. Registrar `uso` (con `cached_tokens` si Meta lo devuelve) en un libro de solo anexar (`brian.uso`).
4. Prohibir por código los modelos o niveles que entrenan con los prompts (ver §2.6).
5. Hacer configurable el proveedor de la vista previa (`vars.BRIAN_PROVEEDOR` en vez del literal `anthropic`).
6. Test con proveedor simulado en formato OpenAI que verifique el cuerpo enviado a Meta (herramientas, imágenes, parámetro de tokens).

## 2. API de Meta (Meta Model API) — qué está verificado y qué no

**Cómo se verificó.** `dev.meta.ai`, `api.meta.ai`, `developer.meta.com`, `openrouter.ai` y `promptfoo.dev` están **bloqueados** por el proxy de este entorno (WebFetch: `EGRESS_BLOCKED`; curl: `connect_rejected`). Se usaron tres vías y cada dato lleva su nivel:

- **[OF-EXTRACTO]**: extracto del buscador de una página **oficial** `dev.meta.ai/docs/...` (texto de Meta, pero no leí la página completa ni su fecha).
- **[OF-REPO]**: repositorio oficial `github.com/meta-models/muse-code-sdk` clonado (último commit 2026-09-30, CHANGELOG leído).
- **[SDK-3º]**: código fuente de paquetes npm de terceros que ya hablan con `api.meta.ai` (descargados con `npm pack` y leídos): `pi-meta-ai@0.1.1`, `pi-muse-spark@0.2.0`, `@nativepi/meta@1.0.2`, `pi-meta-fix@1.0.0`. Meta **no publica un SDK propio** en npm/PyPI (probados `meta-model-api`, `@meta/model-api`, `muse-spark`, … → 404); su documentación dice «apunta el SDK de OpenAI a la base URL».
- **[3º]**: blogs/comparadores → NO VERIFICADO.

### 2.1 Endpoint y compatibilidad

| Dato | Valor | Nivel |
|---|---|---|
| Base URL | `https://api.meta.ai/v1` | [OF-EXTRACTO] (`dev.meta.ai/docs/protocols/chat-completions`, `/docs/quickstart`) + [SDK-3º] (los 4 paquetes) |
| Autenticación | `Authorization: Bearer <clave>`; las claves tienen forma `LLM\|…`; variable sugerida `MODEL_API_KEY` | [SDK-3º] |
| Chat Completions | `POST /v1/chat/completions`, compatible con OpenAI («drop into existing OpenAI code») | [OF-EXTRACTO] |
| Responses API | `POST /v1/responses`, compatible con OpenAI; es la que usan los clientes agénticos (razonamiento cifrado entre turnos, `input_file`) | [OF-EXTRACTO] + [SDK-3º] |
| Límite de salida | `max_completion_tokens` (Chat Completions; `max_tokens` es alias **deprecado**) y `max_output_tokens` (Responses). Los tokens de razonamiento cuentan y se cobran como salida. ⇒ el adaptador actual con `proveedor=openai` manda `max_completion_tokens` (`proveedores.py:243`): **compatible**. | [OF-EXTRACTO] `docs/reasoning` |
| Razonamiento | `reasoning_effort`: `minimal`/`low`/`medium`/`high`/`xhigh` (y `max` en la familia 1.3 según Muse Code). **Muse Spark siempre razona: `"none"` → HTTP 400.** El adaptador actual no manda `reasoning_effort` (usa el defecto del servidor; costo de salida oculto, igual que M-14 de la ronda 2). | [OF-EXTRACTO] + [OF-REPO] CHANGELOG:786 |
| Herramientas | tool calling con llamadas **en paralelo** y en streaming; **`tool_choice` solo acepta `"auto"`** (`"none"`, `"required"` o una función nombrada → 400 «only "auto" is supported for tool_choice»). *Tool search* existe pero no se combina con `json_schema` (400). | [OF-EXTRACTO] `docs/tool-calling`, `docs/tool-search`; [SDK-3º] `pi-meta-fix` |
| Salida estructurada | `response_format` con JSON Schema, modo estricto (`supportsStrictMode`) | [OF-EXTRACTO] + [SDK-3º] |
| Caché de prompt | **automática** por prefijo, sin configuración; Chat Completions informa `usage.prompt_tokens_details.cached_tokens` | [OF-EXTRACTO] `docs/prompt-caching` |
| Conteo de tokens | existe página `docs/token-counting` (endpoint no confirmado) | [OF-EXTRACTO] (solo título) |
| Errores | 429 con `Retry-After`; **402** (saldo/pago) no debe reintentarse | [OF-EXTRACTO] `docs/error-handling`; [OF-REPO] CHANGELOG:758 |

### 2.2 Modelos vigentes

| ID | Contexto | Salida máx. | Entradas | Nivel |
|---|---|---|---|---|
| `muse-spark-1.3` (estándar) | 1 048 576 | 131 072 | texto, imagen, video MP4, PDF (y audio según algunas fuentes) → texto | [OF-EXTRACTO] `docs/models` |
| `muse-spark-1.3-contributor` | igual | igual | igual — **entrena con tus datos** | [OF-EXTRACTO] + [3º] |
| `muse-spark-1.2` / `-1.2-contributor` | 1 048 576 | 131 072 | texto, imagen… | [SDK-3º] `@nativepi/meta` |
| `muse-spark-1.1` | 1 000 000 | 32 000 (64 000 según otro paquete) | texto, imagen | [SDK-3º] |
| Otros de la plataforma: Muse Image (`muse-image-1.0`, por imagen), Muse Voice Transcribe (por minuto), SAM, Muse Glimmer (pesos abiertos, se corre en hardware propio) | — | — | — | [OF-EXTRACTO] `docs/overview` |
| **Llama (Llama 4 Scout/Maverick)** | — | — | — | **La Llama API (`api.llama.com`) se apagó el 2026-07-06** y devuelve respuesta de «sunset»; los pesos siguen abiertos y se sirven por terceros (Groq, Together, Bedrock) y por **Workers AI de Cloudflare**. [OF-EXTRACTO] `llama.developer.meta.com/docs/llama-api-deprecation` + [3º] |

### 2.3 Archivos e imágenes

| Límite | Valor | Nivel |
|---|---|---|
| Imágenes por solicitud | hasta **50** (más → 400) | [OF-EXTRACTO] `docs/image-understanding` |
| Tamaño por imagen en línea (`image_url`, base64/URL) | 50 MB | [OF-EXTRACTO] |
| Por archivo vía Files API (`input_file`) | 1 GiB | [OF-EXTRACTO] |
| Formatos de imagen | jpeg, png, gif, webp, x-icon | [OF-EXTRACTO] |
| PDF | Responses `input_file` (`file_data`/`file_url`/`file_id`); usa el **texto de las primeras 100 páginas** y las **imágenes de las primeras 50 páginas** (que cuentan contra el tope de 50 imágenes) | [OF-EXTRACTO] + [3º] |
| Excel `.xlsx` | no hay soporte nativo documentado → convertir a texto/JSON antes (igual que con Claude; coordina @r3-brian-documentos) | inferido |

Consecuencia práctica: el adaptador Chat Completions actual solo manda imágenes `image_url` en base64 (`proveedores.py:262-264`); **para PDF hace falta la Responses API** (o convertir a imágenes/texto).

### 2.4 Precios (USD por millón de tokens)

| Modelo | Entrada | Entrada en caché | Salida | Nivel |
|---|---|---|---|---|
| `muse-spark-1.3` / `1.2` (estándar) | 1,25 | 0,15 | 4,25 | [3º] coincidente en 5+ fuentes y en el código de `@nativepi/meta` («Source: api.meta.ai/v1 catalog») → **NO VERIFICADO en la página oficial** `docs/pricing-rate-limits` (existe, bloqueada) |
| `…-contributor` | 0,10 | 0,002 | 0,20 | ídem — **prohibido para D'CASA** (ver 2.6) |
| `muse-spark-1.1` | 0 (vista previa gratis en julio 2026) | — | 0 | [SDK-3º]; hoy probablemente de pago (NO VERIFICADO) |

Facturación por uso, sin mínimos; se cobra al alcanzar un umbral o el día 1 de cada mes [OF-EXTRACTO] `docs/pricing-rate-limits`. Hay también una suscripción plana de **Muse Code** (agente de programación), que no aplica a Brian.

### 2.5 Cuotas

[OF-EXTRACTO] `docs/pricing-rate-limits`: por **equipo** (no por clave; varias claves comparten cuota). Estándar **3 000 RPM y 4 000 000 TPM**; Contributor 100 RPM y 3 000 000 TPM; Muse Image 150 RPM. Sobradas para 1 500 interacciones/día.

### 2.6 Uso de datos

- **Estándar** (`muse-spark-1.3`): «not used to improve Meta's products» / «data is never used for training». [OF-EXTRACTO] `docs/models` + [3º].
- **Contributor** (`…-contributor`): Meta **puede entrenar con prompts y respuestas**. El consentimiento va **en el nombre del modelo** (un ID mal escrito en una variable de entorno manda datos de clientes a entrenamiento). [3º] TechTimes 2026-09-04.
- No documentados para ninguno de los dos niveles: días de retención, revisión humana, derecho de borrado, DPA ni cláusulas para transferencia internacional (Ley 81/2019 de Panamá: POR VERIFICAR con abogado, igual que en la ronda 2). [3º]
- **Regla para Brian**: solo IDs de una **lista blanca exacta** (`muse-spark-1.3`), y rechazo por código de cualquier ID que contenga `contributor` (el prototipo lo hace y lo prueba, §5).

### 2.7 Disponibilidad (Panamá)

- Contradictorio y **NO VERIFICADO**: extractos oficiales dicen «Model API isn't available in every country yet» y que Meta «expanded global access to the public preview»; el nivel Contributor está «in select countries». Blogs de septiembre de 2026 hablan de «US-only public preview» (otros dicen que el estándar es global). La lista de países (`dev.meta.ai/help`) no fue legible.
- **Hecho del dueño**: tiene una clave y dice que la usó. Si la cuenta se creó desde Panamá y la llamada respondió, la disponibilidad práctica existe; aun así hay que **confirmar en `dev.meta.ai/help` que Panamá está en la lista** y que los términos permiten uso comercial con datos de terceros.
- Sigue siendo **vista previa pública** (sin SLA conocido): no puede ser el **único** proveedor de Brian.

### 2.8 Veredicto

Meta Muse Spark 1.3 estándar es técnicamente apto como proveedor **principal para conversación y lectura de documentos** (compatible OpenAI, 1M de contexto, 50 imágenes, PDF nativo por Responses, caché automática, precio de entrada ~2,4× más bajo que Sonnet 5.5 y de salida ~2,4× más bajo). Condiciones: (1) solo el ID estándar; (2) confirmar Panamá y términos; (3) fijar `reasoning_effort` (no existe «sin razonar»); (4) nunca enviar `tool_choice` distinto de `auto` (las confirmaciones se hacen en el borde, no forzando herramientas); (5) Claude como respaldo automático por estar en vista previa; (6) medirlo con el arnés de evals de la ronda 2 antes de decidir que es el principal.

## 3. Diseño: Brian nativo en Cloudflare
(pendiente)

## 4. Costos
(pendiente)

## 5. Prototipo
(pendiente)

## 6. Plan de migración
(pendiente)

## 7. Fuentes
(pendiente)
