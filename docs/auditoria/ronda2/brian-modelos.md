# Brian multi-modelo: auditoría de la capa de proveedores y diseño objetivo

Agente: `brian-modelos` (ronda 2) · Fecha de consulta de todas las fuentes: **2026-09-30** · Solo lectura sobre `addons/`, `edge/`, `docker/`, `.github/`.

Leyenda de fuentes (regla ronda 2, punto 2):
- **[OFICIAL-LEÍDA]**: la página oficial del proveedor se descargó y se leyó entera.
- **[OFICIAL-SNIPPET]**: el proxy de salida bloqueó el dominio oficial (`platform.openai.com`, `developers.openai.com`, `openai.com`, `developer.meta.com`, `dev.meta.ai`, `developers.cloudflare.com`, `ai.google.dev`, `openrouter.ai`). Solo vi un extracto del buscador. Sirve de pista, no de prueba.
- **[SECUNDARIA]**: blog, agregador o comparador de precios. Se marca `(NO VERIFICADO)`.

---

## 1. Resumen

1. **Hoy Brian es «un proveedor a la vez, elegido por configuración global»**. Hay dos adaptadores reales (Anthropic y Chat Completions compatible con OpenAI) y uno de pruebas. No hay ruteo por tarea, fallback, streaming, caché de prompts, conteo de tokens ni costos. El `uso` que devuelve el proveedor se descarta (`conversacion.py:272`, confirma B-10).
2. **Lo más caro que se deja en la mesa**: (a) sin `cache_control` el system y los ~45 esquemas de herramientas se pagan completos en cada paso del bucle de 8; (b) el modelo por defecto es Sonnet 5.5 para todo, incluido chat corto y OCR de fotos; (c) no se fija `effort` ni `thinking`, así que Sonnet 5.5 corre pensamiento adaptativo con esfuerzo `high` por defecto y cobra esos tokens como salida.
3. **El punto fuerte que el dueño quiere (Excel, fotos, PDF) es el más débil del código**: `.xlsx` responde «No puedo leer este tipo de archivo» (`conversacion.py:490-491`), el PDF escaneado da «sin texto legible» (`:495`) porque solo se extrae texto con pypdf, y las fotos se mandan en base64 en cada paso del bucle.
4. **Modelos vigentes verificados en fuente oficial (Anthropic)**: Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 4.5 (la Haiku vigente; no hay Haiku 5 en la tabla oficial). Las fechas y precios de OpenAI, Meta, Google y Cloudflare **no pude leerlas en sus páginas oficiales** desde este entorno: van como NO VERIFICADO.
5. **Meta Muse Spark no debe entrar al plan de producción todavía**: la API está en vista previa pública pensada para EE. UU. (hasta donde muestran fuentes secundarias), hay señales contradictorias sobre acceso internacional, y su nivel barato «Contributor» entrena con tus prompts, incompatible con datos de clientes. Se diseña el adaptador (es compatible con OpenAI, según fuentes secundarias) pero se deja **apagado** hasta confirmar Panamá en `dev.meta.ai`.
6. **Recomendación de costo**: enrutar con Haiku 4.5 como base y escalar a Sonnet 5.5, más caché de prompts y Batch para lo no urgente. Con los supuestos de la sección 6, el gasto mensual estimado baja de ~US$23/90/308 (todo Sonnet, sin caché) a ~US$8/29/100 (bajo/medio/alto).
7. **Cloudflare AI Gateway** encaja como capa de observabilidad, tope de gasto y fallback sin tocar la lógica: el código ya acepta `base_url` (`proveedores.py:380`). Su caché es de coincidencia exacta, útil para tareas repetidas y casi inútil para chat de agente.

---

## 2. Hallazgos del código (estado actual de `proveedores.py`)

| # | Tema | Estado hoy | Evidencia (ruta:línea) | Severidad |
|---|---|---|---|---|
| M-01 | Proveedores soportados | Anthropic nativo + «openai» (Chat Completions) usado también para xAI, Groq, OpenRouter, Together y Ollama + `prueba`. **No existe entrada para Meta, Gemini ni Cloudflare Workers AI.** Un `BRIAN_PROVEEDOR` fuera de la tabla deja `tipo=None` y `estado()` dice «falta un proveedor válido». | `proveedores.py:59-76, 368-369, 398-399, 421-427, 340` | MEDIO |
| M-02 | Abstracción de mensajes | Buena: formato neutro (`rol/texto/imagenes/tool_calls/crudo`) con traductores por API. El `crudo` de Anthropic se reenvía solo si el proveedor actual es Anthropic. | `proveedores.py:3-18, 182-219, 257-279`; `conversacion.py:611-613` | BAJO (base sólida) |
| M-03 | Herramientas | Solo `name/description/input_schema`. Sin `strict`/schema estricto, sin `tool_choice`, sin herramientas en paralelo configurables. En OpenAI, JSON de argumentos inválido se degrada a `{'__invalidos__': …}`. | `proveedores.py:175-176, 248-250, 288-293` | BAJO |
| M-04 | Visión por bandera fija | `vision` es constante por proveedor (p. ej. Groq/Together/Ollama `False`) y no por modelo. Un modelo con visión en Groq queda bloqueado; uno sin visión en OpenRouter se intenta igual. | `proveedores.py:61-75, 98`; `conversacion.py:596-597` | MEDIO |
| M-05 | Adjuntos: solo imágenes por visión | Imágenes: base64, tope 5 MB (la API de Anthropic admite 10 MB base64 directo, 5 MB en Bedrock/Google: [OFICIAL-LEÍDA](https://platform.claude.com/docs/en/build-with-claude/vision)). Solo la foto del último mensaje de usuario viaja como imagen; las anteriores se convierten en nota de texto. Se reenvía base64 completo en cada paso (sin Files API). | `conversacion.py:83, 427, 593-601`; `proveedores.py:195-197` | MEDIO |
| M-06 | PDF y Excel | PDF → solo texto con pypdf; escaneado o con tablas-imagen = vacío. `.xlsx` no se lee (el «ms-excel» de `MIMES_TEXTO` es el `.xls` binario y se decodifica como UTF-8 → basura). Tope 20 000 caracteres. Claude acepta PDF nativo (visión por página) y Files API, pero el código no lo usa. | `conversacion.py:82, 88-89, 480-499` | ALTO (núcleo del negocio) |
| M-07 | Streaming | No hay. `requests.post` síncrono devuelve la respuesta completa. El bucle corre dentro de la petición HTTP de Odoo. | `proveedores.py:106-138`; `conversacion.py:255-300` | MEDIO |
| M-08 | Reintentos | 2 reintentos (3 intentos) en 429/5xx/red/timeout, backoff exponencial 1.5 s · 2^n, respeta `retry-after` hasta 10 s, sin *jitter*, sin presupuesto de tiempo global. 4xx no se reintenta. | `proveedores.py:50-52, 106-138` | MEDIO |
| M-09 | Timeouts | `(10, 120)` s por intento. Peor caso ≈ 3 × 120 s × 8 pasos dentro de una sola petición (B-10). | `proveedores.py:50`; `conversacion.py:270` | ALTO (ya en B-10) |
| M-10 | Caché de prompts | No hay. El cuerpo de Anthropic no lleva `cache_control`; el system y las herramientas viajan enteros en cada paso. | `proveedores.py:167-180` | ALTO (costo evitable) |
| M-11 | Tokens y costo | `uso` se mapea a `{entrada, salida}` y **se ignora**. No se leen `cache_read_input_tokens` / `cache_creation_input_tokens`. No hay modelo `brian.uso`, ni tabla de precios, ni `count_tokens`. Estimación local = caracteres / 4. | `proveedores.py:233-235, 298-300`; `conversacion.py:449-453` | ALTO |
| M-12 | Errores y límites | Mensajes en español claros por código HTTP (401/403/404/429/5xx). Límites del lado Brian: 20 mensajes/min, 8 pasos, 12 000 caracteres por resultado. `fin='limite'` (respuesta cortada por `max_tokens` 8000) no se maneja. Sin disyuntor (*circuit breaker*) ni fallback. | `proveedores.py:140-158, 228`; `conversacion.py:79-84, 341-342` | MEDIO |
| M-13 | Selección de modelo | Global: parámetro `dcasa_brian.modelo` o `BRIAN_MODELO`; por defecto `claude-sonnet-5-5`. Clasificación de «modelo pequeño» por subcadena (`'mini'` atrapa `gemini-*`) solo para recortar herramientas. No hay modelo por tarea ni por perfil/rol. | `proveedores.py:55-57, 79, 370, 388-391`; `conversacion.py:407-414` | MEDIO (ya B-21) |
| M-14 | Parámetros de razonamiento | No se envían `thinking` ni `output_config.effort`. Según la guía de la API de Claude que carga este entorno, Sonnet 5.5 sin `thinking` corre adaptativo con esfuerzo `high`, y no admite `thinking: {type: "disabled"}` (400). Es costo de salida oculto en cada paso. (NO probado contra la API real: no hay clave aquí.) | `proveedores.py:167-180` | MEDIO |
| M-15 | «Pensamiento» y recorte de historial | La guía de la API indica que los bloques de pensamiento están atados al modelo y a la conversación, y que en cuentas nuevas (creadas desde 2026-08-31) editar turnos anteriores da 400. `_historial_neutro` recorta por ventana deslizante y sustituye imágenes antiguas por notas: edita turnos previos. Riesgo a **probar** antes de depender de Sonnet 5.5 con historiales largos. (Fuente: guía interna del skill `claude-api`, no leí la página oficial.) | `conversacion.py:421-439, 593-597` | POR VERIFICAR |
| M-16 | Secretos | La clave se lee primero de entorno; `configuracion()` la devuelve a cualquier usuario interno (B-02, ya reportado). Con varios proveedores habrá varias claves: hay que guardarlas por proveedor, no una sola `BRIAN_API_KEY`. | `proveedores.py:381`; `brian.md` B-02 | ALTO (ya B-02) |
| M-17 | Proveedor de pruebas | Determinista y sin red; sirve de base para pruebas de ruteo y fallback. | `proveedores.py:304-337` | POSITIVO |

Notas de contexto. `max_tokens=8000` es razonable para no-streaming. El diseño de perfiles con `modelo_ia` y `tope_tokens_dia` ya está propuesto en `docs/auditoria/brian.md` §6.2 (líneas 353-370); este informe lo extiende a ruteo por tarea y costo.

---

## 3. Investigación: modelos, capacidades y precios

### 3.1 Anthropic (Claude) — fuente oficial leída

Fuentes: [Pricing](https://platform.claude.com/docs/en/about-claude/pricing), [Vision](https://platform.claude.com/docs/en/build-with-claude/vision), [PDF](https://platform.claude.com/docs/en/build-with-claude/pdf-support), [Batch](https://platform.claude.com/docs/en/build-with-claude/batch-processing), [Regiones](https://platform.claude.com/docs/en/api/supported-regions), [Retención](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention). Consulta: 2026-09-30. Precios en USD por millón de tokens (MTok).

| Modelo (ID) | Contexto | Entrada | Escritura caché 5 min | Lectura caché | Salida | Batch entrada / salida | Notas |
|---|---|---|---|---|---|---|---|
| Claude Fable 5.1 (`claude-fable-5-1`) | 1M | 10 | 12.50 | 0.25 | 50 | 5 / 25 | El más capaz; fuera de presupuesto |
| Claude Opus 5.5 (`claude-opus-5-5`) | 1M | 4 | 5 | 0.20 | 20 | 2 / 10 | Razonamiento fuerte; uso excepcional |
| Claude Sonnet 5.5 (`claude-sonnet-5-5`) | 1M | 2 | 2.50 | 0.20 | 10 | 1 / 5 | Hoy el defecto de Brian |
| Claude Sonnet 5 (`claude-sonnet-5`) | 1M | 2 | 2.50 | 0.20 | 10 | 1 / 5 | El precio de $2/$10 quedó como estándar (no sube a $3/$15) |
| Claude Haiku 4.5 (`claude-haiku-4-5`) | 200K | 1 | 1.25 | 0.10 | 5 | 0.50 / 2.50 | La Haiku vigente; base de costo |

Otros datos oficiales:
- Escritura de caché de 1 hora = 2× la entrada; lectura = 0.1× (0.05× en Opus 5.5; 0.025× en Fable 5.1). Batch y caché se pueden combinar.
- Batch: 50 % de descuento; máx. 100 000 solicitudes o 256 MB por lote; casi siempre termina en menos de 1 h, expira a las 24 h; resultados disponibles 29 días.
- Visión: JPEG/PNG/GIF/WebP; 10 MB por imagen (base64) en la API directa; 8000×8000 px; hasta 600 imágenes por solicitud (100 en modelos de 200K de contexto como Haiku 4.5); si hay más de 20 imágenes, recomienda ≤2000 px por lado; 32 MB por solicitud. Costo = ⌈ancho/28⌉×⌈alto/28⌉ tokens; nivel estándar (Haiku 4.5) tope 1568 tokens por imagen; nivel alta resolución (Claude 4.7 y posteriores, incluye Sonnet 5.5) hasta 4784 tokens.
- PDF nativo: 32 MB, 600 páginas (100 si el contexto es menor a 1M, como Haiku 4.5); ~1 500 a 3 000 tokens de texto por página más la imagen de la página. **Binarios como `.xlsx` no se aceptan en bloques de documento: hay que convertirlos a texto o PDF.** Files API para subir una vez y referenciar.
- Uso de herramientas: cada solicitud con `tools` suma un prompt de sistema de 286 tokens (Sonnet 5.5 y Opus 5.5) y 496 (Haiku 4.5), más los esquemas.
- Datos: la página de Visión dice que los uploads de imágenes son efímeros y que Anthropic no los usa para entrenar; la de retención declara que lo retenido nunca se usa para entrenar sin permiso expreso. La cifra de días de retención estándar está en `privacy.claude.com` (**no la leí: NO VERIFICADO**). ZDR existe por acuerdo; algunos modelos (los «Covered Models», p. ej. Fable) exigen retención.
- Disponibilidad: **Panamá aparece en la lista oficial de regiones compatibles** de la API.
- Residencia: `inference_geo: "us"` cuesta 1.1× (modelos 4.6 y posteriores).
- Salida estructurada, herramientas y `strict`: confirmados por la guía de API de este entorno (`output_config.format`, `strict: true`); no leí la página oficial de structured outputs.
- Límites de tasa por nivel (Start/Build/Scale): página oficial no leída, **NO VERIFICADO**.

### 3.2 OpenAI — solo extractos (proxy bloqueó el dominio oficial)

Páginas oficiales bloqueadas: `platform.openai.com`, `developers.openai.com`, `openai.com`. Precios de fuentes secundarias (consulta 2026-09-30): [metacto](https://www.metacto.com/blogs/unlocking-the-true-cost-of-openai-api-a-deep-dive-into-usage-integration-and-maintenance), [pricepertoken GPT-5.4 mini](https://pricepertoken.com/pricing-page/model/openai-gpt-5.4-mini), [OpenRouter GPT-5.4 nano](https://openrouter.ai/openai/gpt-5.4-nano).

| Modelo | Contexto | Entrada | Entrada en caché | Salida | Estado |
|---|---|---|---|---|---|
| GPT-5.5 | 1M | 5.00 | 0.50 | 30.00 | (NO VERIFICADO) |
| GPT-5.4 | 1M | 2.50 | 0.25 | 15.00 | (NO VERIFICADO) |
| GPT-5.4 mini | 400K | 0.75 | 0.075 | 4.50 | (NO VERIFICADO) |
| GPT-5.4 nano | 400K | 0.20 | 0.02 | 1.25 | (NO VERIFICADO) |

- Batch y Flex: 50 % de descuento (fuente secundaria, NO VERIFICADO).
- Algunos resultados de búsqueda hablan de «GPT-5.6» y «GPT-6»: **no sé cuál es hoy el modelo insignia**. No recomiendo un ID de OpenAI sin leer `developers.openai.com/api/docs/models`.
- Chat Completions y Responses API soportan JSON Schema (`response_format: json_schema`, `additionalProperties:false`, todos los campos `required`) según el extracto de la guía oficial de Structured Outputs (resultado de búsqueda, no leída entera). Visión, PDF como entrada y límites de archivo de OpenAI: no verificados.
- Datos: el extracto de ayuda oficial indica que los datos de la API no se usan para entrenar por defecto y se retienen hasta 30 días para detección de abuso (NO VERIFICADO; ZDR por calificación).
- Panamá: aparece en la lista «API supported countries and territories» (extracto de `help.openai.com`, **[OFICIAL-SNIPPET]**).

### 3.3 Meta Muse Spark — sin lectura oficial

Dominios oficiales (`developer.meta.com`, `dev.meta.ai`) bloqueados. Todo lo siguiente es de buscador o blogs (NO VERIFICADO): [buscador → developer.meta.com blog](https://developer.meta.com/ai/resources/blog/build-with-muse-spark/), [OpenRouter 1.1](https://openrouter.ai/meta/muse-spark-1.1), [techjacksolutions](https://techjacksolutions.com/ai-tools/muse-spark/muse-spark-pricing/), [eesel 1.3](https://www.eesel.ai/blog/muse-spark-1-3), [techtimes](https://www.techtimes.com/articles/326714/20260904/meta-muse-spark-contributor-tier-hides-training-consent-where-security-tools-cannot-find-it.htm).

| Dato | Valor reportado | Estado |
|---|---|---|
| Versiones | 1.1 (lanzada 2026-07-09, vista previa pública), 1.2, **1.3 (2026-09-02)**; IDs `muse-spark-1.3` y `muse-spark-1.3-contributor` | (NO VERIFICADO) |
| Contexto | 1 048 576 tokens | (NO VERIFICADO) |
| Entradas | texto, imagen, video, audio y PDF; salida texto | (NO VERIFICADO) |
| Funciones | herramientas (también en paralelo), salida estructurada, búsqueda con citas, esfuerzo de razonamiento configurable | (NO VERIFICADO) |
| Precio estándar | 1.25 entrada / 4.25 salida; caché 0.15 | (NO VERIFICADO) |
| Nivel «Contributor» | 0.10 / 0.20 **a cambio de permiso para entrenar con prompts y respuestas** | (NO VERIFICADO) |
| Compatibilidad | formato OpenAI; base `https://api.meta.ai/v1`, clave `Bearer` | (NO VERIFICADO) |
| Disponibilidad | «vista previa pública para desarrolladores de EE. UU.»; fuentes contradictorias: una dice sin lista de espera y otra dice lista de espera; una dice «acceso global ampliado»; una dice «no en OpenRouter» mientras existen páginas de OpenRouter | **Panamá: NO VERIFICADO; asumir no disponible** |
| Batch / caché de 5 min / límites de archivo | no encontrado | NO VERIFICADO |

Conclusión: no hay evidencia oficial de disponibilidad en Panamá ni de la política de datos. Conservar el adaptador en la lista **desactivado**, y revisar `dev.meta.ai/docs/models` desde un entorno sin bloqueo antes de activarlo. **Nunca usar el nivel Contributor con datos de D'CASA.**

### 3.4 Alternativas baratas

**Google Gemini** (extracto de buscador, NO VERIFICADO): [precios](https://www.morphllm.com/gemini-api-pricing), [regiones](https://ai.google.dev/gemini-api/docs/available-regions). Gemini 2.5 Flash-Lite ≈ 0.10 entrada / 0.40 salida por MTok, batch -50 %. Panamá aparece en la lista de países del API según el extracto. Hay modelos Gemini 3.x más nuevos citados en títulos; no sé cuál es el Flash vigente. La política de datos del nivel gratis vs. de pago: NO VERIFICADO.

**Cloudflare Workers AI** (extractos, NO VERIFICADO): [Cloudflare docs, pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/index.md) — 10 000 neuronas gratis al día en planes Free y Paid; US$0.011 por 1 000 neuronas adicionales (plan Paid). Por modelo, un calculador de terceros da Llama 3.2 11B Vision ≈ 0.0485 entrada / 0.676 salida por MTok ([typingmind](https://custom.typingmind.com/tools/estimate-llm-usage-costs/cloudflare-workers-ai/llama-3-2-11b-vision-instruct)). Ventaja: el dato no sale de Cloudflare y no hay clave externa. Desventaja: calidad de OCR y de herramientas en español muy inferior a Claude/GPT-mini para tablas y comprobantes. **Uso recomendado: clasificador barato, resumen de títulos, enmascarado previo; no extracción de facturas.** Validar con la evaluación de `brian-evals`.

### 3.5 Cloudflare AI Gateway (extractos, NO VERIFICADO salvo nota)

Fuentes: [Spend limits (docs)](https://developers.cloudflare.com/ai-gateway/features/spend-limits/), [Custom costs (docs)](https://developers.cloudflare.com/ai-gateway/configuration/custom-costs/), [changelog 2026-06-05](https://developers.cloudflare.com/changelog/post/2026-06-05-spend-limits/), [TrueFoundry resumen de precios](https://www.truefoundry.com/blog/cloudflare-ai-gateway-pricing). Todo leído solo por extractos.
- Funciones: analíticas (peticiones, tokens, costo, errores, latencia), caché, límite de tasa (ventana fija o deslizante, 429 al excederlo), reintento y **fallback** entre proveedores, *dynamic routing*, guardrails, DLP, BYOK (tus propias claves), **spend limits** por dólares (por modelo, proveedor o metadato como `user_id`), **custom costs** para tus tarifas negociadas. Anthropic, OpenAI y Google están entre los proveedores.
- Precio: analíticas, caché y límite de tasa gratis en todos los planes; se paga por logs persistentes más allá de la cuota del plan, Logpush, guardrails y una comisión del 5 % si usas facturación unificada (NO VERIFICADO; no leí los límites de logs del plan).
- Caché: clave = hash de la solicitud completa, coincidencia exacta; TTL máx. 1 mes. Para un agente con historial cambiante casi nunca pega; sí sirve para tareas idénticas repetidas.
- **Riesgo de privacidad**: si se activan logs, el gateway guarda prompts y respuestas (datos de clientes) en Cloudflare. Hay que decidir la retención de logs (NO VERIFICADO el nombre exacto del control).
- Cómo se conecta: en el código actual basta poner `BRIAN_BASE_URL` a la URL del gateway por proveedor (el adaptador de Anthropic arma `{base_url}/v1/messages`, `proveedores.py:179`). Nombres exactos de ruta y cabeceras (`cf-aig-*`) **no verificados**: confirmar en la documentación antes de codificar.

---

## 4. Diseño de la capa multi-modelo

### 4.1 Principios

1. **Un solo contrato neutro, muchos adaptadores** (ya existe; se amplía a adjuntos y a «tarea»).
2. **El ruteo es configuración (datos), no código**: tabla `brian.ruta` editable por el administrador, con precios en un archivo de datos con URL y fecha (al estilo de `puntos.json`: sin cifra fuera del archivo, `null` = pendiente).
3. **El libro de uso es de solo anexar**, igual que `dcasa.movimiento`: `brian.uso` no tiene saldo; el gasto del mes es la suma.
4. **Por defecto, lo barato; escalar solo con evidencia de fallo.**
5. **Los datos de clientes solo van a proveedores aprobados** (lista blanca por clase de dato).

### 4.2 Interfaz común

```python
# proveedores.py (propuesta)
Solicitud = {
  'tarea': 'chat_corto' | 'excel' | 'vision_foto' | 'extraccion' | 'agente' | 'lote',
  'sistema': str,                      # bloque estable (se cachea)
  'mensajes': [...],                   # formato neutro actual
  'herramientas': [...],               # o None
  'adjuntos': [{'mimetype','datos'|'archivo_id','nombre','clase_dato'}],
  'esquema_salida': dict | None,       # JSON Schema para extracción estructurada
  'urgente': bool,                     # False => elegible para Batch
  'limite_salida': int, 'esfuerzo': 'low'|'medium'|'high',
  'usuario_id', 'perfil_id', 'accion_id',   # para costo y topes
}
Respuesta = {'texto','tool_calls','fin','datos_estructurados',
             'uso': {'entrada','salida','cache_lectura','cache_escritura'},
             'modelo_usado','proveedor_usado','crudo'}
```

Capacidades declaradas **por modelo** (no por proveedor): `vision`, `pdf_nativo`, `schema_estricto`, `herramientas`, `batch`, `cache_prompt`, `contexto`, `max_imagen_mb`. Arregla M-04 y M-13. Para OpenAI-compatible: adaptador único con `base_url`; Anthropic nativo aparte (caché, PDF y Batch son específicos).

### 4.3 Matriz tarea → modelo (valores iniciales a validar con `brian-evals`)

| Tarea | Base (barato) | Escala a | Fallback entre proveedores | Notas |
|---|---|---|---|---|
| Chat corto / consultas de lectura | Haiku 4.5, `effort` bajo | Sonnet 5.5 si la herramienta falla o el usuario pide «revisa» | GPT-5.4 mini (NO VERIFICADO) | Caché del bloque system+herramientas |
| Constructor / acciones sensibles | Sonnet 5.5 | Opus 5.5 (manual, tope) | GPT-5.4 (NO VERIFICADO) | Siempre con confirmación humana; no bajar de Sonnet |
| Lectura de Excel (celdas, fórmulas, tablas) | **Código primero** (openpyxl → JSON compacto); el LLM solo interpreta | Sonnet 5.5 para hojas ambiguas | GPT mini | Coordinar con `brian-excel`; binarios no van a la API, hay que convertirlos |
| Imágenes incrustadas en celdas y fotos de producto | Haiku 4.5 (1 568 tokens máx. por imagen) | Sonnet 5.5 (hasta 4 784 tokens, más detalle) | Gemini Flash-class (NO VERIFICADO) | Reducir a ≤2000 px; subir a Files API si se reusa |
| OCR de comprobantes/PDF escaneado | PDF nativo a Haiku 4.5 | Sonnet 5.5 | GPT mini con imágenes | 100 páginas máx. en Haiku 4.5 |
| Extracción estructurada (factura → JSON) | Haiku 4.5 con `output_config.format` / schema | Sonnet 5.5 tras 2 fallos de validación | OpenAI `json_schema` (NO VERIFICADO) | Validar en Odoo con el mismo schema |
| Agente con herramientas | Sonnet 5.5 (con `effort` medio) | Opus 5.5 solo manual | GPT-5.4 | Bucle con presupuesto de pasos/tokens |
| Lotes no urgentes (descripciones de catálogo, reclasificación) | Haiku 4.5 **Batch** | Sonnet 5.5 Batch | OpenAI Batch (NO VERIFICADO) | -50 %; resultado hasta 24 h |

### 4.4 Escalada y fallback

- **Escalada vertical** (mismo proveedor, modelo más capaz): 2 JSON inválidos contra el schema; herramienta pedida con argumentos inválidos dos veces; `fin='limite'`; etiqueta de tarea «estructura»; usuario pulsa «Revisa a fondo». Cada escalada se registra como gasto propio.
- **Fallback horizontal** (otro proveedor): tras agotar reintentos por 429/5xx/timeout, o con disyuntor abierto (p. ej. 3 fallos en 60 s → 5 min sin usar ese proveedor). Al cambiar de proveedor se descarta `crudo` (el código ya lo hace, `conversacion.py:611-613`) y los bloques de pensamiento no se pasan.
- **Presupuesto de tiempo por turno** (deadline 90 s) en lugar de reintentos ciegos (ver B-10).
- **Streaming** hacia el panel: solo vale la pena cuando el bucle salga de la petición HTTP de Odoo (Worker/Queue; ver `brian-eventos`).

### 4.5 Caché de prompts

1. Anthropic: `cache_control` en el bloque system y en el último esquema de herramientas (prefijo estable primero; lo variable, al final). Verificar `cache_read_input_tokens > 0`. Lectura = 0.1× en Sonnet 5.5 y Haiku 4.5. Un prefijo mínimo cacheable existe por modelo: NO VERIFICADO el valor para estos modelos (la guía local dice 512-4 096 tokens según el modelo); medir.
2. Con 12 herramientas para modelos pequeños (`HERRAMIENTAS_MODELO_PEQUENO`, `conversacion.py:85`) el prefijo cambia por mensaje (`catalogo(consulta=…)`): eso **rompe la caché**. Fijar el subconjunto por conversación o por perfil, no por mensaje.
3. OpenAI cachea el prefijo automáticamente (precio de entrada en caché en §3.2, NO VERIFICADO); Meta tiene precio de caché reportado; Gemini: no verificado.
4. AI Gateway: caché exacta solo para tareas idénticas (p. ej. «descripción de producto X» repetida).

### 4.6 Batch

`enviar_lote(solicitudes)` → `brian.lote` (proveedor, id externo, estado) → `ir.cron` (o Queue) consulta hasta `ended`, y escribe resultados por `custom_id` (nunca por posición) en `brian.uso` con costo de lote. Candidatos: importación masiva de Excel de catálogo, descripciones, clasificación de gastos, auditorías nocturnas. Anthropic: 50 % de descuento, máx. 100 000 solicitudes o 256 MB, ≤24 h, resultados 29 días ([OFICIAL-LEÍDA](https://platform.claude.com/docs/en/build-with-claude/batch-processing)). Límite: Batch no sirve para chat en vivo.

### 4.7 AI Gateway: papel recomendado

Usarlo como **cinturón de seguridad**, no como el cerebro: analíticas de costo por proveedor, fallback de emergencia, *spend limit* mensual duro por metadato (segundo freno tras el tope en Odoo) y límite de tasa. El tope fino por usuario/rol vive en Odoo porque necesita perfil y contexto de negocio. Mantener `BRIAN_BASE_URL` por proveedor para poder quitar el gateway sin tocar código. Decidir explícitamente si se guardan logs con prompts (datos de clientes).

### 4.8 Topes de gasto y registro de costo por acción

```text
brian.uso (solo anexar)            brian.modelo.precio (datos versionados)
- fecha, usuario, perfil, canal    - proveedor, modelo, vigente_desde, fuente_url, fecha_consulta
- tarea, proveedor, modelo         - entrada, salida, cache_lectura, cache_escritura  (null = PENDIENTE)
- tokens: entrada, salida,         - batch_factor
  cache_lectura, cache_escritura
- costo_usd (congelado al escribir, con la versión de precio)
- conversacion_id, accion_id (brian.accion), lote_id, intento, escalada_de
```

- Cada llamada escribe una fila; cada `brian.accion` suma las filas de sus llamadas («esta factura costó US$0.03»).
- **Topes**: por usuario/día, por perfil/día (`tope_tokens_dia` ya propuesto, `brian.md:365`, pasar a dólares), por mes global, y por tarea (un lote no puede gastar más que X). Comportamiento: 80 % → aviso; 100 % → degradar a modelo barato; 120 % → bloquear con mensaje en español.
- **Antes de llamar**: estimar con la heurística actual o `count_tokens` de Anthropic; negarse si una sola llamada proyecta pasar el tope.
- **Semáforo de costo** en Ajustes › Brian (propuesta de UI ya en `brian.md` §6).
- Regla análoga a Socios: ninguna cifra de precio fuera del archivo de datos; sin columna de saldo.

---

## 5. Riesgos

| Riesgo | Detalle | Mitigación |
|---|---|---|
| **Privacidad de clientes (Ley 81/2019)** | Nombres, teléfonos, RUC, montos y fotos de comprobantes salen a un tercero en EE. UU. Extracto de fuentes secundarias: la Ley 81 de 2019 entró en vigor el 2021-03-29, el Decreto Ejecutivo 285 de 2021 la reglamenta y, según el resumen, las transferencias internacionales exigen país de protección adecuada o garantías como cláusulas contractuales tipo ([ICAZA](https://icazalaw.com/es/2021/07/ley-de-proteccion-de-datos-personales-y-su-reglamento-en-panama/), [ANTAI](https://antai.gob.pa/reglamentan-ley-81-de-proteccion-de-datos-personales/)). **POR VERIFICAR con abogado panameño**: base legal/consentimiento, necesidad de contrato (DPA) con cada proveedor y aviso en la política de privacidad. | Máscara de RUC/teléfono por perfil (ya propuesto, `brian.md` línea ~236); lista blanca de proveedores por clase de dato; registro de qué se envió; DPA firmado antes de producción. |
| **Entrenamiento con tus datos** | Anthropic: lo retenido no se usa para entrenar sin permiso y las imágenes no se usan (oficial, leído). OpenAI: no entrena con la API por defecto (extracto, NO VERIFICADO). **Meta Contributor: entrena por diseño (NO VERIFICADO pero coincidente en 5 fuentes)**. Gemini nivel gratis: NO VERIFICADO. | Prohibir en código cualquier ruta cuyo nombre contenga `contributor`; bloquear nivel gratis de terceros con datos reales; Workers AI como opción que no sale de Cloudflare (NO VERIFICADO sus términos). |
| **Retención** | Anthropic: días estándar NO VERIFICADO (página de `privacy.claude.com` no leída); ZDR por acuerdo. OpenAI: hasta 30 días por abuso (NO VERIFICADO). Logs del AI Gateway: retención configurable (NO VERIFICADO). | Documentar cuánto retiene cada proveedor tras leer sus páginas; desactivar logs de contenido en el gateway. |
| **Dependencia de un proveedor** | Hoy casi todo depende de Anthropic. Un cambio de precio o de política (p. ej. el Sonnet 5 casi sube a $3/$15 y luego se mantuvo en $2/$10, [OFICIAL-LEÍDA](https://platform.claude.com/docs/en/about-claude/pricing)) mueve el costo. | Contrato neutro + fallback; evals por tarea en al menos dos proveedores; precios en datos. |
| **Cambios de API/modelos** | Los modelos nuevos rechazan parámetros viejos (`budget_tokens`, `thinking: disabled`, `tool_choice` forzado, prefill) según la guía local. | Adaptador por familia de modelo con pruebas de humo semanales. |
| **Disponibilidad geográfica** | Anthropic y OpenAI listan Panamá; Gemini lo lista (extracto); Meta no confirmado. | Activar solo proveedores verificados en Panamá. |
| **Inyección desde archivos** | Excel/PDF/fotos traen texto que puede intentar dar órdenes. Ya hay marcado como DATO (`conversacion.py:475-476`). | Mantener; añadir prueba con un Excel malicioso (con `brian-evals`). |
| **Costo oculto de razonamiento** | Sin `effort`, Sonnet 5.5 usa pensamiento adaptativo a `high`. | Fijar `effort` por tarea y medir salida real. |

---

## 6. Costo mensual estimado (3 perfiles)

Precios: los de §3.1 (oficiales, 2026-09-30). **Son supuestos míos, no mediciones**; hay que reemplazarlos con los datos reales de `brian.uso` cuando exista.

### 6.1 Supuestos por unidad de trabajo

| Unidad | Supuestos de tokens |
|---|---|
| Mensaje de chat (agente) | 2.5 llamadas por mensaje; prefijo estable 6 000 tokens (system + herramientas) + 3 000 de historial/consulta por llamada; salida 400 tokens por llamada (sin pensamiento extra) |
| Excel/PDF extraído | 40 000 tokens de entrada (texto + ~20 imágenes chicas) + 3 000 de salida |
| Foto / comprobante suelto | 2 000 de entrada (imagen ~1 500 + texto) + 500 de salida |
| Ítem de lote | 3 000 de entrada + 500 de salida, con -50 % Batch |
| Caché | Prefijo de 6 000 tokens siempre caliente (lectura a 0.1× en Haiku 4.5, 0.1× en Sonnet 5.5); las escrituras iniciales se ignoran |

Costo unitario resultante (USD; Haiku 4.5 / Sonnet 5.5):

| Unidad | Haiku 4.5 | Sonnet 5.5 |
|---|---|---|
| Chat sin caché | 0.0275 | 0.0550 |
| Chat con caché | 0.0140 | 0.0280 |
| Excel/PDF (interactivo / Batch) | 0.055 / 0.0275 | 0.110 / 0.055 |
| Foto | 0.0045 | 0.0090 |
| Ítem de lote (Batch) | 0.00275 | 0.0055 |

### 6.2 Perfiles de uso mensual (tienda pequeña, 2 a 5 usuarios internos)

| Perfil | Mensajes de chat | Excel/PDF | Fotos | Ítems de lote |
|---|---|---|---|---|
| Bajo | 400 | 10 | 30 | 0 |
| Medio | 1 500 | 40 | 150 | 200 |
| Alto | 5 000 | 150 | 600 | 1 000 |

### 6.3 Escenarios (USD/mes)

- **A (hoy)**: todo Sonnet 5.5, sin caché, sin Batch.
- **B**: todo Sonnet 5.5 con caché.
- **C (diseño recomendado)**: chat 80 % Haiku 4.5 + 20 % Sonnet 5.5 con caché; Excel/PDF 70 % Batch Sonnet 5.5 + 30 % interactivo; fotos en Haiku 4.5; lotes Haiku 4.5 Batch.

| Perfil | A (hoy) | B (+caché) | C (ruteado + Batch) |
|---|---|---|---|
| Bajo | ≈ 23 | ≈ 13 | **≈ 8** |
| Medio | ≈ 90 | ≈ 50 | **≈ 29** |
| Alto | ≈ 308 | ≈ 173 | **≈ 100** |

Sensibilidades:
- Si Sonnet 5.5 genera 1 000 tokens de salida por llamada (pensamiento a `high`) en vez de 400, el chat con caché pasa de US$0.028 a ≈ US$0.043 (+54 %); el escenario B «medio» subiría a ≈ US$70.
- Con 100 % de las solicitudes de Excel urgentes (sin Batch) el escenario C «alto» sube unos US$6.
- Precios de referencia de otros proveedores para chat con caché con los mismos supuestos: GPT-5.4 mini ≈ 0.011/mensaje, Muse Spark estándar ≈ 0.016/mensaje, Gemini 2.5 Flash-Lite ≈ 0.003/mensaje, GPT-5.4 nano ≈ 0.003/mensaje (todos NO VERIFICADOS; tokens de imagen y calidad de OCR difieren y no están comparados).
- No incluido: impuestos, comisión 5 % del Gateway con facturación unificada (NO VERIFICADO), logs del Gateway, Workers/Queues, IVA sobre servicios del exterior.
- El ahorro de la escalera Haiku→Sonnet **depende de que Haiku 4.5 alcance calidad** en las herramientas de D'CASA: medirlo antes de fijar 80/20.

---

## 7. Plan de implementación sugerido (en orden)

1. `brian.uso` + tabla de precios en datos + leer `cache_*` del `usage` (M-11). Es lo que cierra B-10 y permite medir.
2. `cache_control` en Anthropic y subconjunto de herramientas estable por conversación (M-10). Medición con `cache_read_input_tokens`.
3. `effort` y `max_tokens` por tarea (M-14); manejar `fin='limite'` (M-12).
4. Tabla `brian.ruta` (tarea → modelo) y capacidades por modelo (M-04, M-13); modelo por perfil (`brian.md` §6.2).
5. PDF nativo y lectura de `.xlsx` (con `brian-excel`) (M-06); Files API para fotos repetidas (M-05).
6. Fallback entre proveedores con disyuntor y deadline por turno (M-08, M-09).
7. `enviar_lote` con Anthropic Batch y `ir.cron` (con `brian-eventos`).
8. Gateway de Cloudflare como capa opcional vía `BRIAN_BASE_URL`; tope de gasto duro mensual.
9. Adaptador Meta (OpenAI-compatible) **desactivado** hasta verificar Panamá y política de datos.
10. Pruebas: usar el proveedor `prueba` para ruteo/fallback/topes sin red; evals reales con `brian-evals`.

---

## 8. NO VERIFICADO (lista consolidada)

- Toda la página oficial de OpenAI (precios, modelo insignia vigente, PDF/visión, límites de archivo, retención, Batch). El proxy bloqueó `platform.openai.com`, `developers.openai.com`, `openai.com`.
- Toda la documentación oficial de Meta (`dev.meta.ai`, `developer.meta.com`): versiones, precios, caché, batch, límites de archivo, disponibilidad fuera de EE. UU., política de datos. Las fuentes secundarias se contradicen en acceso.
- Precios y modelo vigente de Gemini; política de datos del nivel gratis; existencia de modelos Gemini 3.x.
- Precios por modelo y política de datos de Workers AI; calidad de sus modelos con visión en español.
- Documentación oficial de Cloudflare AI Gateway (rutas exactas, cabeceras `cf-aig-*`, cuotas de logs, costo de logs, forma de desactivar el registro de contenido). Solo extractos.
- Días de retención estándar de Anthropic y de OpenAI; ZDR para estos modelos en D'CASA.
- Límites de tasa por nivel de Anthropic; prefijo mínimo cacheable para Haiku 4.5 y Sonnet 5.5.
- Comportamiento de `thinking`/`effort` de Sonnet 5.5 y del chequeo de «pensamiento preservado» contra la API real (solo guía local del skill `claude-api`; sin clave de API en este entorno).
- Ley 81/2019 y Decreto 285/2021: aplicabilidad a estos envíos, transferencia internacional, contratos necesarios. **Consulta legal pendiente.**
- Todos los números de las cuentas de la §6: son supuestos.

## 9. Coordinación con otros agentes

- `brian-excel`: M-06 (`.xlsx` no se lee; PDF escaneado vacío; binarios no aceptados en bloques de documento de Claude, hay que convertirlos) y el costo por archivo de la §6.
- `brian-eventos`: M-07/M-09 (bucle síncrono, sin streaming ni deadline), `enviar_lote` con Queue/cron, costo por invocación.
- `brian-evals`: fijar 80/20 Haiku/Sonnet y probar extracción con schema, Excel malicioso y OCR de comprobantes antes de cambiar el defecto.
