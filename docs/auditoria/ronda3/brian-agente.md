# Ronda 3 · `r3-brian-agente` — Brian nativo en Cloudflare con Meta como proveedor

> Agente `r3-brian-agente`, ronda 3. Fecha: 2026-10-01. Prototipo en `docs/auditoria/ronda3/brian-agente/`.

## 0. Resumen ejecutivo

1. **Cómo se probó a Brian con Meta**: no hay rastro verificable. Nunca existió un proveedor `meta` en el código; la única corrida «desde GitHub Actions» con Brian y clave es la Previsualización #33 (2026-09-30, 60 min), que arranca Odoo con `BRIAN_PROVEEDOR=anthropic` fijo. O el secreto es de Anthropic (y lo que gustó fue Claude Sonnet 5.5), o el dueño cambió en Ajustes › Brian a «OpenAI» con la dirección de Meta (Ajustes gana a la variable; la clave del entorno gana a la de Ajustes). **Hay que preguntárselo.** Hoy se conecta sin tocar código con `BRIAN_PROVEEDOR=openai`, `BRIAN_BASE_URL=https://api.meta.ai/v1`, `BRIAN_MODELO=muse-spark-1.3` (§1).
2. **API de Meta** (dev.meta.ai bloqueado; extractos oficiales + código de 4 clientes que ya la usan + repo oficial `meta-models`): compatible con OpenAI (Chat Completions y Responses), `muse-spark-1.3` con 1 M de contexto y 131 072 de salida, texto/imagen/video/PDF (PDF por Responses), 50 imágenes por solicitud, caché automática, herramientas en paralelo y JSON Schema; **solo `tool_choice:"auto"`** y **siempre razona**. La Llama API (`api.llama.com`) se apagó el 2026-07-06. Precio 1,25/0,15/4,25 USD por MTok **NO VERIFICADO**. El nivel `-contributor` entrena con los prompts: prohibido por código. Disponibilidad en Panamá: contradictoria (§2).
3. **Diseño**: un Agent (Durable Object con SQLite) por conversación, un DO único para el libro de costo y los topes, AI Gateway delante de todo (métricas sin payload, Meta como *custom provider*), Odoo como ejecutor y autoridad por JSON-2 con la clave de cada persona, confirmación humana firmada por Odoo, Workflows para tareas largas, R2 para archivos, MCP con `createMcpHandler` (`McpAgent` está deprecado) (§3).
4. **Costo**: el borde cuesta **≈ $0** sobre los $5 del plan a 50, 300 y 1 500 interacciones/día; todo el gasto son tokens. Ruta recomendada 80 % Meta + 20 % Sonnet 5.5 ≈ **$19 / $98 / $447 al mes** frente a $34 / $173 / $792 con solo Sonnet 5.5 (supuestos en §4; Meta NO VERIFICADO). Lo que más ahorra es achicar el prefijo de herramientas (catálogo por paquetes de r3-brian-habilidades) y mantenerlo estable para la caché.
5. **Prototipo**: TypeScript con `agents` 0.24.0; `npm run typecheck` en verde y **31/31 pruebas** (29 en Node + 2 en workerd real) cubren proveedores Meta/Claude, idempotencia, confirmación con caducidad, respaldo, disyuntor, topes y libro de solo agregar (§5).
6. **Migración en 6 fases** con el bucle de Odoo como respaldo; la fase 1 (Meta bien conectado + `brian.uso` + caché, dentro de Odoo) da la mayor parte del ahorro en días; la fase 0 (cerrar la puerta RPC) es obligatoria antes que todo (§6).

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
| `BRIAN_BASE_URL` / Dirección del API | `https://api.meta.ai/v1` (sin `/chat/completions`: el adaptador lo añade, `proveedores.py:251`) |
| `BRIAN_MODELO` / Modelo | `muse-spark-1.3` (nunca un ID con `contributor`) |
| `BRIAN_API_KEY` (secreto) | la clave de Meta |
| `BRIAN_HERRAMIENTAS_MAX` | `0` (todas) — un ID con `lite`/`mini`/`8b` en el nombre activaría la preselección de 12 (`:79`, `:388-391`) |

Trampas del atajo (por qué «conectarlo así» no es «hacerlo bien»):

- Con `proveedor=openai` el adaptador manda `max_completion_tokens` (`proveedores.py:243`), que es el parámetro vigente en Meta (`max_tokens` es alias deprecado, §2.1): **compatible**. Pero no manda `reasoning_effort` (Muse Spark razona con el valor por defecto del servidor: costo de salida no controlado) y con `MAX_TOKENS = 8000` (`:53`) el razonamiento cuenta dentro de ese tope.
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

Skills oficiales leídas antes de diseñar (`cf-skills/skills/`): `agents-sdk` (SKILL.md + callable, durable-execution, workflows, human-in-the-loop, mcp, streaming-chat, state-scheduling, queue-retries, observability), `durable-objects` (SKILL.md + rules, testing), `workers-best-practices`, `wrangler`. Cifras de la plataforma: §4.2 (doc oficial vía MCP).

### 3.1 Arquitectura

```text
 Panel Odoo (OWL) ──WebSocket+JWT corto──┐
 Telegram ──webhook (secret_token)───────┤      Cloudflare (Workers Paid, ya necesario para el sitio)
 Claude/Cursor (MCP) ──OAuth / clave─────┤
                                         ▼
                              Worker de entrada (auth, ruteo; 0 estado)
                                         │ getAgentByName(`${persona}:${conversación}`)
                                         ▼
          ┌──────────── BrianConversacion (Agent = Durable Object + SQLite propio) ────────────┐
          │ mensajes (solo se agregan) · herramientas fijadas al inicio · pendientes con caducidad│
          │ resultados por id de llamada (idempotencia) · bucle de herramientas · streaming     │
          └───────┬──────────────────────────┬──────────────────────────────┬───────────────────┘
                  │ RPC                      │ fetch (BYOK)                  │ JSON-2 con la clave de la PERSONA
                  ▼                          ▼                               ▼
        LibroUso (1 DO, empresa)     AI Gateway (métricas sin payload,   Odoo 19 (ejecutor y autoridad:
        libro de tokens/costo,       custom cost, rate limit, 2.º freno)  ACL, reglas, idem_key, token de
        topes persona/rol/global      ├─ custom-meta → api.meta.ai/v1      confirmación para lo sensible)
                                      ├─ anthropic  → Claude 5.5 / Haiku
                                      └─ openai     → (PENDIENTE)
        Workflows: tareas largas y aprobaciones (importar Excel → proponer → waitForEvent → aplicar)
        R2: archivos originales · Queues: copia del libro a Odoo (`brian.uso`) y referencias de archivos
```

### 3.2 Piezas y decisiones

| Pieza | Decisión | Por qué (evidencia) |
|---|---|---|
| Agente | **Un Agent (DO con SQLite) por conversación**, nombre `persona:conversación`. Estado: historial que solo se agrega, herramientas fijadas al iniciar, pendientes, resultados por id. | Skill `durable-objects`: «one DO per entity», `getByName` determinista, SQLite. El historial append-only es además obligatorio para Claude 5.5 (editar turnos invalida el pensamiento y en cuentas nuevas da 400; skill `claude-api`). |
| Libro y topes | **Un DO `LibroUso` para toda la empresa** (el presupuesto es el átomo de coordinación). Libro de solo agregar en microdólares con `version_precios`; el gasto es la suma (como `dcasa.movimiento`). Copia nocturna a Odoo por Queue para reportes. | Un DO por conversación no puede sumar el mes de una persona. Volumen máximo ≈ 4 500 escrituras/día: trivial para un DO. |
| Topes | por **rol de la persona/mes**, **global/mes**; ≥ 80 % → ruta económica; ≥ 100 % → bloqueo con mensaje en español; precio `null` (PENDIENTE) → ese modelo no se usa. Segundo freno: *spend limit* de AI Gateway (solo para modelos con precio conocido; es «eventually consistent»). | Doc oficial de spend limits (§4.2). Cifras de tope = decisión del dueño (en el prototipo son de ejemplo). |
| Proveedores | Capa propia con formato neutro (heredero de `proveedores.py`): Meta y OpenAI por Chat Completions compatible; Claude por Messages API nativa (caché explícita, `effort`, `fallbacks: "default"`, bloques crudos reenviados sin tocar). | Las diferencias reales (tool_choice, effort, caché, pensamiento preservado) no caben en un «OpenAI para todos»; el Universal Endpoint de AI Gateway está deprecado. |
| Ruteo | Tabla de rutas como **datos**: principal = Meta `muse-spark-1.3` → respaldo Claude Sonnet 5.5; económica = Claude Haiku 4.5. Disyuntor (3 fallos → 60 s). Un 400 no salta de proveedor (es error nuestro). OpenAI entra cuando su precio y términos estén verificados. | Meta en vista previa sin SLA conocido (§2.7). Tareas «difíciles» (contabilidad, cierre) pueden fijar Sonnet 5.5 como principal cuando las evals lo digan. |
| Caché de prompt | Prefijo **estable**: sistema sin hora/nombre/pantalla + herramientas ordenadas y fijadas por conversación; lo variable en `<contexto>` dentro del mensaje de usuario. Claude: `cache_control` en sistema y última herramienta (+ recomendable `cache_control` de nivel superior para cachear también el historial). Meta: caché automática. Paquetes nuevos de habilidades con `cargar_habilidad` que solo **agrega** (Meta no tiene `defer_loading`). | Hallazgos de brian-evals (ronda 2) y r3-brian-habilidades. Haiku 4.5 solo cachea prefijos ≥ 4 096 tokens; Sonnet/Opus 5.5 ≥ 512 (skill `claude-api`). |
| Ejecutor | **Odoo por JSON-2 con la clave de API de cada persona** (`Authorization: bearer`), nunca sudo ni «token de servicio». Odoo es la **autoridad**: devuelve el catálogo de herramientas permitido para esa persona y canal al iniciar la conversación (r3-brian-habilidades: `decidir()`), revalida en cada ejecución y guarda `idem_key` único. | Hallazgo ALTO de brian-eventos (ronda 2) y RESPUESTA de r3-brian-habilidades. En el prototipo el perfil se simula con `persona.areas`. |
| Confirmación humana | Herramienta `sensible` ⇒ tarjeta con resumen ya resuelto, **caduca a los 10 min**, solo la persona que la originó la confirma, transición atómica `pendiente→ejecutando` antes del `await` (dos clics = una ejecución). En producción Odoo **firma** la tarjeta (token HMAC de un solo uso) y `ejecutar_externo` exige ese token: así ni un borde comprometido ni la clave de una persona permiten saltarse la confirmación. | B-03 y B-04 reproducidos por r3-brian-habilidades (`confirmado=True` por RPC). |
| Idempotencia | `idem` = id de la llamada de herramienta, en el DO (tabla `resultados`) **y** en Odoo (`brian.accion.idem_key` único). Los reintentos del modelo, de Workflows o de la red no duplican cobros ni cotizaciones. | Skill `agents-sdk/workflows`: «make retried operations idempotent». |
| Tareas largas | **Workflows**: `extraer` (≤ 30 min por paso) → `proponer` → `step.waitForEvent` (aprobación; las instancias en espera no cuentan para la concurrencia) → `aplicar` por lotes con `idem` por fila → informe. Archivos en **R2**; los pasos devuelven referencias (≤ 1 MiB por resultado). | Doc oficial de límites de Workflows (§4.2). Interfaz de archivos coordinada con @r3-brian-documentos (pregunta en bitácora). |
| Streaming | Panel ↔ agente por **WebSocket** (hibernable) y `@callable({ streaming: true })`, o `AIChatAgent` si se adopta el AI SDK; el proveedor con `stream: true`. Telegram: el Worker responde 200 de inmediato y el DO procesa (dedupe de `update_id` en su SQLite). | Skill `agents-sdk/streaming-chat`; hallazgo de brian-eventos (Telegram espera al modelo). **No prototipado**. |
| MCP | `createMcpHandler` (sin estado) con OAuth/clave por persona; **mismo contrato** de herramientas; las sensibles devuelven «confirmar fuera de banda». | `McpAgent` está **deprecado** (Agents SDK v0.20.0, 2026-07-27, doc oficial). |
| Observabilidad | Workers Logs + Traces (`observability.enabled` y `traces.enabled`), AI Gateway con `cf-aig-collect-log-payload: false` y `cf-aig-metadata` {persona, rol, conversación} (máx. 5 entradas). | Skill `workers-best-practices`; privacidad (Ley 81/2019, POR VERIFICAR con abogado). |

### 3.3 Contrato de herramientas (común con @r3-brian-habilidades y @r3-brian-documentos)

Implementado en `src/nucleo/herramientas.ts`:

```ts
interface Herramienta {
  nombre: string;                 // snake_case estable (renombrar rompe caché y evals)
  descripcion: string;
  esquema: JSONSchema;            // additionalProperties:false + required (sirve a `strict` de Claude y Meta)
  nivel: "lectura" | "construccion" | "sensible";
  area: string;                   // en producción: `paquete` del catálogo de r3-brian-habilidades
  resumir?(args): string;         // texto de la tarjeta con valores resueltos (B-09)
  ejecutar(args, { odoo, persona, idem }): Promise<unknown>;   // siempre por JSON-2 con la clave de la persona
}
```

Acordado en bitácora con r3-brian-habilidades: el mismo `esquema()` neutro de Odoo + metadatos (`paquete`, `grupos`, `nivel_ayuda_min`, `reversible`, `externo`), catálogo declarativo `catalogo_habilidades.yaml`, y **Odoo decide qué herramientas ve cada persona y canal** (el borde no decide permisos con su copia). Para archivos propongo a r3-brian-documentos: `leer_archivo({ref, hoja?, rango?, pagina?})` → JSON intermedio comprimido con `celda_origen`, donde `ref` apunta a R2 y el trabajo pesado corre fuera del isolate (128 MB).

### 3.4 Qué hace falta en Odoo (lado ejecutor)

1. Fase 0 de seguridad (prerrequisito, ya reproducida por r3-brian-habilidades): métodos de `brian.*` privados.
2. `brian.herramientas.catalogo_externo(canal)` y `ejecutar_externo(nombre, args, idem, token_confirmacion=None)` por JSON-2, **sin** parámetro `confirmado`.
3. `brian.accion.idem_key` con `models.Constraint` único; reintento con la misma clave devuelve el resultado guardado.
4. Emisión de JWT corto para el WebSocket del panel y de la clave de API con alcance `brian` por persona (vencimiento; se guarda cifrada AES-GCM en el DO).
5. `brian.uso` (solo lectura en Odoo, alimentado por Queue desde `LibroUso`) para el semáforo de costo en Ajustes › Brian.

## 4. Costos

### 4.1 Tokens (por interacción y por mes)

Guion reproducible: `docs/auditoria/ronda3/brian-agente/costos/calcular.py` (salida en `costos/salida.txt`), con los precios de `data/precios.json`.

**Supuestos** (no medidos contra la API: no hay claves aquí): interacción típica = 1 mensaje que usa 1 herramienta = 2 llamadas; prefijo estable 3 500 tokens (sistema + herramientas del perfil, cifra coherente con la medición de r3-brian-habilidades: 2 100-3 900 tokens de herramientas + núcleo); contexto e historial 1 500; resultado de herramienta 800; salida 400 + 300 tokens (incluye razonamiento a esfuerzo bajo). Prefijo «tibio» en la primera llamada del turno: 30 % / 70 % / 90 % para 50 / 300 / 1 500 interacciones al día. Mismos conteos de tokens para todos los modelos (en realidad los tokenizadores difieren: los Claude 4.7+ producen ~30 % más tokens para el mismo texto, doc oficial de precios).

| Modelo (estado del precio) | Sin caché | Con caché 50/día | 300/día | 1 500/día |
|---|---|---|---|---|
| Meta `muse-spark-1.3` (**NO VERIFICADO**) | $0,0170 | $0,0103 | $0,0088 | $0,0080 |
| Claude Haiku 4.5 (oficial) | $0,0147 | $0,0147 | $0,0147 | $0,0147 |
| Claude Sonnet 5.5 (oficial) | $0,0294 | $0,0224 | $0,0192 | $0,0176 |
| Claude Opus 5.5 (oficial) | $0,0588 | $0,0440 | $0,0372 | $0,0339 |

USD por mes (30 días, con caché):

| Ruta | 50/día | 300/día | 1 500/día |
|---|---|---|---|
| Solo Meta 1.3 | 15,48 | 79,02 | 360,45 |
| Solo Haiku 4.5 | 22,05 | 132,30 | 661,50 |
| Solo Sonnet 5.5 | 33,65 | 172,94 | 792,23 |
| Solo Opus 5.5 | 65,94 | 335,16 | 1 524,60 |
| **80 % Meta + 20 % Sonnet 5.5** (respaldo/escalado) | **19,11** | **97,80** | **446,81** |

Lectura: (1) con estos supuestos Meta cuesta ~45-55 % de Sonnet 5.5 por interacción; (2) **Haiku 4.5 no es más barato que Sonnet 5.5 con caché** porque su mínimo cacheable (4 096 tokens) es mayor que el prefijo de 3 500: sin caché paga todo a precio lleno; (3) el rubro que más mueve el costo es el tamaño del prefijo de herramientas: el catálogo por paquetes de r3-brian-habilidades (−44 a −73 % de tokens de herramientas) vale más que cambiar de modelo; (4) OpenAI no se calcula: precio PENDIENTE (dominio oficial bloqueado). Precios oficiales de Claude leídos el 2026-10-01 en https://platform.claude.com/docs/en/about-claude/pricing (Haiku 4.5: 1 / 1,25 / 0,10 / 5; Sonnet 5.5: 2 / 2,50 / 0,20 / 10; Opus 5.5: 4 / 5 / 0,20 / 20 USD/MTok entrada / escritura 5 min / lectura / salida; Batch −50 %; sobrecarga de tool use 286 tokens en Sonnet/Opus 5.5 y 496 en Haiku 4.5).

### 4.2 Capa Cloudflare (doc oficial vía MCP, consultada 2026-10-01)

| Producto | Incluido en Workers Paid ($5/mes, que la cuenta necesita igual para el sitio) | Excedente | Fuente (Last updated) |
|---|---|---|---|
| Workers | 10 M solicitudes, 30 M ms CPU/mes | $0,30/M; $0,02/M ms | https://developers.cloudflare.com/workers/platform/pricing/ (2026-08-28) |
| Durable Objects | 1 M solicitudes, 400 000 GB-s/mes; SQLite: 25 mil M filas leídas, 50 M escritas, 5 GB-mes | $0,15/M; $12,50/M GB-s; $1/M filas escritas; $0,20/GB-mes | https://developers.cloudflare.com/durable-objects/platform/pricing/ |
| Workflows | 10 M solicitudes, 30 M ms CPU, 500 000 pasos, 1 GB-mes | $0,80/100 000 pasos; $0,20/GB-mes | https://developers.cloudflare.com/workflows/reference/pricing/ (2026-09-21) |
| Queues | 1 M operaciones/mes (≈ 3 por mensaje) | $0,40/M | https://developers.cloudflare.com/workers/platform/pricing/ |
| R2 | 10 GB-mes, 1 M clase A, 10 M clase B, egreso gratis | $0,015/GB-mes | https://developers.cloudflare.com/r2/pricing/ (2026-08-07) |
| Workers Logs + Traces | 20 M eventos/mes, 7 días (Traces se cobran desde 2026-10-01 con la misma cuota) | $0,60/M | https://developers.cloudflare.com/workers/observability/logs/workers-logs/ |
| AI Gateway | analítica, caché, rate limiting, DLP: gratis; logs de gateways nuevos = Workers Logs | Logpush $0,05/M; Unified Billing +5 % (no se usa: BYOK) | https://developers.cloudflare.com/ai-gateway/reference/pricing/ (2026-09-24) |

Consumo estimado por interacción: ~1,1 solicitudes al Worker, ~7 al DO (1 al agente + RPC al libro; optimizable a 3), 1-2,5 GB-s (128 MB × 8-20 s de espera al modelo: un DO con E/S pendiente cuenta duración), ~8 filas escritas, ~15 KB guardados, ~5-10 eventos de log/traza.

| | 50/día | 300/día | 1 500/día |
|---|---|---|---|
| Solicitudes DO/mes | 10 500 | 63 000 | 315 000 (< 1 M) |
| GB-s/mes (2,5 por interacción) | 3 750 | 22 500 | 112 500 (< 400 000) |
| Filas escritas/mes | 12 000 | 72 000 | 360 000 (< 50 M) |
| Almacenamiento nuevo/mes | 23 MB | 135 MB | 675 MB (5 GB incluidos ≈ 7 meses; luego centavos; política de retención de 90 días para conversaciones, el libro no se borra) |
| **Costo marginal Cloudflare** | **$0** | **$0** | **$0** (dentro de lo incluido) |

Conclusión: el borde cuesta ≈ $0 sobre los $5 que ya se pagan; **todo el gasto real son tokens**, y el primer límite del plan en acercarse es la duración de DO (≈ 3,5 veces el volumen alto). Coincide con brian-eventos (ronda 2) y lo confirmó r3-cf-plataforma en bitácora.

### 4.3 Total mensual (tokens + Cloudflare marginal)

| Volumen | Ruta recomendada (80 % Meta + 20 % Sonnet 5.5) | Alternativa sin Meta (Sonnet 5.5) |
|---|---|---|
| 50/día | ≈ $19 | ≈ $34 |
| 300/día | ≈ $98 | ≈ $173 |
| 1 500/día | ≈ $447 | ≈ $792 |

(Más los $5 de Workers Paid, compartidos con el sitio. Cifras de Meta NO VERIFICADAS; las de Claude, oficiales.)

## 5. Prototipo (`docs/auditoria/ronda3/brian-agente/`)

TypeScript, paquete `agents` 0.24.0 de Cloudflare, `wrangler` 4.145.0, `vitest` 5.0.3. **No se desplegó nada** (regla de la auditoría; solo `wrangler deploy --dry-run`).

### 5.1 Estructura

| Archivo | Qué hace |
|---|---|
| `src/nucleo/tipos.ts` | Formato neutro (mensajes, llamadas, uso con caché, `Proveedor`, `Persona`). Sin dependencias de Cloudflare. |
| `src/nucleo/bucle.ts` | Clase `Brian`: turno con bucle de herramientas (máx. 6 pasos), historial que solo se agrega, herramientas fijadas al iniciar, confirmaciones, idempotencia, registro en el libro. |
| `src/nucleo/enrutador.ts` | Ruteo por datos (principal Meta → Sonnet 5.5; económica Haiku), respaldo, disyuntor, degradación al 80 % del tope. |
| `src/nucleo/libro.ts` | Libro de uso de solo agregar en microdólares + topes por rol/persona/mes y global. |
| `src/nucleo/acciones.ts` | Pendientes con caducidad (10 min) y transiciones atómicas; resultados por id de llamada. |
| `src/nucleo/herramientas.ts` | Contrato común + 4 herramientas de ejemplo (`buscar_productos`, `consultar_cliente` = lectura; `crear_cotizacion` = construcción; `registrar_pago` = sensible). |
| `src/nucleo/odoo.ts` | `OdooJson2` (clave de la persona, `/json/2/<modelo>/<método>`, cabecera de idempotencia) y `OdooSimulado` (datos de ejemplo, no de D'CASA). |
| `src/nucleo/prompt.ts` | Prefijo estable y bloque `<contexto>` variable (hora de Panamá, persona, pantalla). |
| `src/nucleo/precios.ts` + `data/precios.json` | Tabla de precios con `fuente` y `consultado`; `null` = PENDIENTE (no se rellena; el modelo no se usa); cabecera `cf-aig-custom-cost`. |
| `src/proveedores/openai_compat.ts` | Meta (y OpenAI): `max_completion_tokens`, `reasoning_effort`, nunca `tool_choice`, lista blanca y **veto a `*contributor*`**, cabeceras de AI Gateway sin payload. |
| `src/proveedores/anthropic.ts` | Claude: `cache_control` en sistema y última herramienta, `output_config.effort` (no en Haiku), `fallbacks: "default"` en 5.5, bloques crudos reenviados sin tocar. |
| `src/proveedores/simulado.ts` | Proveedor determinista con guion (incluye errores HTTP). |
| `src/agente.ts`, `src/libro_do.ts`, `src/index.ts`, `src/sql_do.ts`, `wrangler.jsonc` | Capa Cloudflare: `BrianConversacion extends Agent`, `LibroUso extends DurableObject` (RPC), Worker de entrada con HMAC de identidad (comparación con `crypto.subtle.verify`), observabilidad y trazas activadas. |
| `test/*.test.ts` | 29 pruebas en Node (núcleo y proveedores, SQL real con `node:sqlite`) + 2 en **workerd real** (`wrangler dev` local, sin cuenta) que corren el núcleo dentro de un Durable Object con su SQLite. |
| `costos/calcular.py` | Cálculo de §4.1. |

### 5.2 Cómo ejecutarlo

```bash
cd docs/auditoria/ronda3/brian-agente
npm ci                      # o npm install
npm run typecheck           # tsc del Worker (workers-types) y de los tests (node)
npm test                    # vitest: 31 pruebas (BRIAN_SIN_WORKERD=1 omite las 2 de workerd)
npx wrangler deploy --dry-run --outdir /tmp/brian-dist   # empaqueta; NO despliega
python3 costos/calcular.py
```

### 5.3 Salida real (2026-10-01)

```text
$ npm run typecheck
> brian-agente-prototipo@0.1.0 typecheck
> tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.test.json

exit=0

$ npx vitest run --reporter=verbose
RUN  v5.0.3 /home/user/D_Casa_new_word/docs/auditoria/ronda3/brian-agente

 ✓ test/proveedores.test.ts > precios (data/precios.json) > calcula microdólares exactos con caché (Sonnet 5.5 oficial) 7ms
 ✓ test/proveedores.test.ts > precios (data/precios.json) > un precio PENDIENTE no se rellena: lanza 1ms
 ✓ test/proveedores.test.ts > precios (data/precios.json) > cada precio lleva fuente y fecha 1ms
 ✓ test/proveedores.test.ts > precios (data/precios.json) > arma cf-aig-custom-cost por token para AI Gateway 6ms
 ✓ test/proveedores.test.ts > Meta (Chat Completions compatible) > manda max_completion_tokens y reasoning_effort, nunca tool_choice; imágenes como image_url 136ms
 ✓ test/bucle.test.ts > bucle de herramientas > lectura: ejecuta en Odoo con idem = id de la llamada y registra el costo en el libro 33ms
 ✓ test/bucle.test.ts > bucle de herramientas > prefijo estable: sistema y herramientas idénticos entre turnos y horas; lo variable va en <contexto> 3ms
 ✓ test/bucle.test.ts > bucle de herramientas > idempotencia: si el modelo repite el mismo id de llamada, Odoo no ejecuta dos veces 3ms
 ✓ test/bucle.test.ts > bucle de herramientas > perfil: a la vendedora no se le ofrece ni se le ejecuta registrar_pago 4ms
 ✓ test/bucle.test.ts > bucle de herramientas > valida argumentos: campo no permitido vuelve como error al modelo, no a Odoo 3ms
 ✓ test/bucle.test.ts > confirmación humana de acciones sensibles > crea la tarjeta con el resumen resuelto, NO ejecuta, y no gasta otra llamada al modelo 10ms
 ✓ test/bucle.test.ts > confirmación humana de acciones sensibles > confirmar ejecuta una sola vez; repetir devuelve el mismo resultado sin volver a Odoo 4ms
 ✓ test/bucle.test.ts > confirmación humana de acciones sensibles > dos confirmaciones simultáneas: una ejecuta y la otra ve «en_curso» 2ms
 ✓ test/bucle.test.ts > confirmación humana de acciones sensibles > caduca a los 10 minutos y ya no se puede ejecutar 3ms
 ✓ test/bucle.test.ts > confirmación humana de acciones sensibles > otra persona no puede confirmar; cancelar deja constancia en la conversación 2ms
 ✓ test/bucle.test.ts > confirmación humana de acciones sensibles > si Odoo niega el permiso (ACL de la persona), la acción queda «fallida» y no se reintenta sola 2ms
 ✓ test/bucle.test.ts > ruteo, respaldo y topes de gasto > si Meta falla (503), responde Claude Sonnet y el libro lo anota a nombre de Anthropic 2ms
 ✓ test/bucle.test.ts > ruteo, respaldo y topes de gasto > un 400 es error nuestro: no se reintenta en otro proveedor 1ms
 ✓ test/bucle.test.ts > ruteo, respaldo y topes de gasto > un modelo con precio PENDIENTE no se usa (no se puede medir) y se pasa al siguiente 2ms
 ✓ test/bucle.test.ts > ruteo, respaldo y topes de gasto > al 80 % del tope pasa a la ruta económica (Haiku); al 100 % bloquea con mensaje en español 4ms
 ✓ test/bucle.test.ts > ruteo, respaldo y topes de gasto > disyuntor: tras 3 fallos seguidos de Meta, durante 60 s ni se intenta 3ms
 ✓ test/bucle.test.ts > reglas del libro > el código del libro no tiene UPDATE ni DELETE sobre `uso` (solo se agrega) 1ms
 ✓ test/proveedores.test.ts > Meta (Chat Completions compatible) > prohíbe cualquier modelo «contributor» (entrena con los prompts) sin llamar a la red 6ms
 ✓ test/proveedores.test.ts > Meta (Chat Completions compatible) > 402 (sin saldo) no es reintentable; 429 sí 7ms
 ✓ test/proveedores.test.ts > Meta (Chat Completions compatible) > argumentos JSON inválidos no rompen el bucle 1ms
 ✓ test/proveedores.test.ts > Anthropic (Messages API) > cachea system y la ÚLTIMA herramienta; effort en output_config; fallback de servidor en Sonnet 5.5 3ms
 ✓ test/proveedores.test.ts > Anthropic (Messages API) > Haiku 4.5 no recibe effort (no lo admite) 1ms
 ✓ test/proveedores.test.ts > Anthropic (Messages API) > reenvía sin tocar los bloques crudos de un turno anterior de Claude (pensamiento preservado) 9ms
 ✓ test/proveedores.test.ts > Odoo JSON-2 > usa la clave de la PERSONA y manda la clave de idempotencia 2ms
 ✓ test/workerd.test.ts > núcleo de Brian dentro de un Durable Object (workerd) > turno con herramienta + confirmación idempotente + libro en el SQLite del DO 68ms
 ✓ test/workerd.test.ts > núcleo de Brian dentro de un Durable Object (workerd) > el estado del DO persiste: repetir el mismo guion en la MISMA conversación no vuelve a cobrar 48ms

 Test Files  3 passed (3)
      Tests  31 passed (31)
   Start at  00:23:07
   Duration  3.81s (tests 77%, transform 19%, import 4%, worker 1%)

exit=0
```

`npx wrangler deploy --dry-run`: «Total Upload: 2319.40 KiB / gzip: 431.04 KiB», enlaces `BrianConversacion` y `LIBRO` (Durable Objects) + variables; «--dry-run: exiting now». El paquete `agents` pesa la mayor parte (bien dentro de los límites del plan).

### 5.4 Qué demuestran las pruebas (y qué no)

- Demuestran: cuerpo exacto que se manda a Meta y a Claude; veto a modelos que entrenan con los datos; caché por prefijo estable; idempotencia por id de llamada (también entre reinicios del DO, en workerd); tarjeta de confirmación sin ejecutar ni gastar otra llamada; caducidad, doble clic concurrente, persona equivocada, cancelación y ACL negada por Odoo; respaldo Meta→Claude y que un 400 no salta de proveedor; precio PENDIENTE ⇒ modelo no usado; degradación al 80 % y bloqueo al 100 % del tope; libro sin UPDATE/DELETE; el mismo SQL corre en `node:sqlite` y en el SQLite de un DO.
- **No** demuestran: calidad de Meta frente a Claude (hace falta el arnés de evals de la ronda 2 con claves reales), formato real de las respuestas de `api.meta.ai` (solo extractos y SDK de terceros), streaming, Telegram, MCP, Workflows y la autenticación JWT del panel (diseñados, no prototipados). `@cloudflare/vitest-pool-workers` 0.22 pide vitest ^4 (aquí vitest 5): por eso la integración usa `wrangler dev` local.
- Simplificaciones a corregir antes de producción: el perfil se simula con `persona.areas` (en producción la lista la da Odoo); el libro autoriza antes y registra después (una ráfaga concurrente puede pasar el tope por una llamada: aceptable, o reservar costo estimado); `autorizar` se llama 2 veces por llamada (juntar en una RPC); la confirmación aún no la firma Odoo.

## 6. Plan de migración (Brian en Odoo → Brian en el borde)

Principio: **todo cambio en Odoo es aditivo** y el bucle actual (`conversacion.py`) queda como respaldo hasta la última fase. Los tests de `dcasa_brian` (hoy 77 funciones `test_` en 6 archivos; el mandato habla de 91: conteo por confirmar con `scripts/test.sh dcasa_brian`) se mantienen verdes en cada fase; el proveedor `prueba` no se toca.

| Fase | Qué se hace | Dónde | Respaldo / criterio de salida |
|---|---|---|---|
| **0. Seguridad** (prerrequisito) | Métodos de `brian.*` privados (`_…`/`@api.private`), test que recorre `brian.*` buscando métodos públicos; nada de `confirmado=` por RPC. | Odoo | Reproducido por r3-brian-habilidades (CRÍTICO). Sin esto, ninguna fase siguiente tiene sentido. |
| **1. Meta bien conectado dentro de Odoo** | Proveedor `meta` en `PROVEEDORES` (tipo `openai`, `https://api.meta.ai/v1`, `muse-spark-1.3`), claves por proveedor, veto a `contributor`, `reasoning_effort`, registrar `uso` (con `cached_tokens`) en `brian.uso` + `data/precios.json`, prefijo estable (hora/usuario/pantalla fuera del sistema), `BRIAN_PROVEEDOR` de la vista previa como variable. | Odoo | Cambiar el proveedor vuelve a Claude en Ajustes. Salida: evals de la ronda 2 (`brian-evals-prototipo`) con Meta vs Sonnet 5.5, en dólares por caso, umbrales propuestos (exactitud ≥ 0,95, alucinación ≤ 0,02, críticos = 0). |
| **2. Ejecutor externo en Odoo** | `catalogo_externo(canal)`, `ejecutar_externo(nombre, args, idem, token)`, `idem_key` único, token de confirmación firmado, clave de API con alcance `brian` por persona, JWT corto para el panel. Bloquear en el Worker público las rutas internas. | Odoo + `edge/` | Tests nuevos del ejecutor; el bucle de Odoo sigue siendo el único usado. |
| **3. Borde en sombra** | Desplegar Worker + `BrianConversacion` + `LibroUso` + AI Gateway (logs sin payload). Telegram pasa al borde (200 inmediato, dedupe en DO). Bandera por persona `BRIAN_MOTOR=odoo|borde` (dueña primero). | Cloudflare | Si el borde falla, el panel sigue en Odoo; Telegram puede volver al webhook de Odoo cambiando una URL. Salida: 2 semanas sin acciones duplicadas y libro cuadrado contra los paneles de Meta/Anthropic. |
| **4. Panel y MCP en el borde** | Chat del panel por WebSocket al agente con streaming; MCP con `createMcpHandler`; Workflows para importar Excel (con @r3-brian-documentos) y otras tareas largas con aprobación; R2 para adjuntos. | Cloudflare + OWL | El botón de Brian cae al endpoint de Odoo si el WebSocket no conecta (respaldo automático). |
| **5. Odoo solo ejecuta** | El bucle de Odoo queda como modo respaldo (desactivado por defecto), sin borrar sus tests; Odoo conserva herramientas, permisos, auditoría (`brian.accion`) y reportes de costo. | Odoo | Volver atrás = cambiar la bandera. |

Orden de valor/costo: la fase 1 da el 80 % del ahorro (Meta + caché + libro) en días y sin infraestructura nueva; las fases 3-4 dan robustez (Telegram sin timeouts, transacciones cortas, streaming, tareas largas) y casi no cuestan dinero (§4.2).

## 7. Fuentes (consultadas 2026-10-01)

**Oficiales leídas completas**
- Anthropic, precios: https://platform.claude.com/docs/en/about-claude/pricing (WebFetch). Skill `claude-api` (tabla de modelos cacheada 2026-09-25; mínimos de caché; `effort`, `fallbacks`, pensamiento preservado, `tool_choice`).
- Cloudflare (MCP `search_cloudflare_documentation`): AI Gateway pricing y limits (Last updated 2026-09-24), spend limits (2026-09-30), custom costs (2026-09-09), logging (2026-09-24), custom providers, chat-completion (2026-08-07), universal (deprecado, 2026-09-14), request handling (2026-09-14); Workers pricing (2026-08-28); Durable Objects pricing; Workflows pricing (2026-09-21) y limits; R2 pricing (2026-08-07); Workers Logs y Traces; Agents: human-in-the-loop, remote MCP server, migrate to MCP SDK v2, changelog Agents SDK v0.20.0 (2026-07-27). Skills oficiales en `cf-skills/skills/`.
- GitHub (MCP): ejecuciones del workflow Previsualización de `dcasapty/D_Casa_new_word` (#33, id 36734759699, job 109953770510).
- Repo oficial de Meta `github.com/meta-models/muse-code-sdk` (clonado; CHANGELOG: 402/429 de Meta Model API, esfuerzo `max` en 1.3).

**Oficiales solo por extracto de buscador** (dominio bloqueado: `dev.meta.ai`, `api.meta.ai`): `dev.meta.ai/docs/protocols/chat-completions`, `/docs/models`, `/docs/image-understanding`, `/docs/reasoning`, `/docs/prompt-caching`, `/docs/tool-calling`, `/docs/tool-search`, `/docs/pricing-rate-limits`, `/docs/error-handling`, `/help`; `llama.developer.meta.com/docs/llama-api-deprecation/`.

**Código de terceros leído** (`npm pack`): `pi-meta-ai@0.1.1`, `pi-muse-spark@0.2.0`, `@nativepi/meta@1.0.2`, `pi-meta-fix@1.0.0`.

**Terceros (NO VERIFICADO)**: eesel.ai, codersera.com, miraflow.ai, techtimes.com (2026-09-04), zentor.ai, opensourcefactory.dev, empiriolabs.ai, layer3labs.io, developersdigest.tech, spheron.network.

### NO VERIFICADO (resumen)
Precios de Meta (1,25 / 0,15 / 4,25) · disponibilidad en Panamá y términos comerciales de Meta · retención de datos del nivel estándar de Meta · comportamiento real de `api.meta.ai` con herramientas e imágenes (solo extractos y SDK de terceros) · precios y términos de OpenAI · si los *spend limits* de AI Gateway aplican a un custom provider con `cf-aig-custom-cost` · qué proveedor usó realmente el dueño en la vista previa #33.
