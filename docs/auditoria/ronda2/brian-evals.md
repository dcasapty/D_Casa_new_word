# Brian: evaluación, tokens y arnés de pruebas (ronda 2, agente `brian-evals`)

Fecha: 2026-09-30 · Método: lectura estática de `addons/dcasa_brian` (sin arrancar Odoo: `vendor/odoo` está vacío), lectura del Excel real con `openpyxl 3.0.9`, consulta de fuentes oficiales y secundarias. Solo lectura sobre `addons/`, `edge/`, `docker/`, `.github/`; todo lo nuevo vive en `docs/auditoria/ronda2/`.

Convención: `(NO VERIFICADO)` = no pude confirmarlo con una fuente vigente o con una medición propia. Los tokens de este informe son **estimaciones**: no hay clave de API en el entorno, así que no usé el endpoint de conteo de tokens (ver sección 3).

## 1. Resumen

1. **Hoy Brian no puede leer un `.xlsx`.** El adjunto `.xlsx` cae en «(No puedo leer este tipo de archivo.)» (`conversacion.py:89-91, 487-491`). Solo entra texto plano/CSV/JSON y PDF con texto. No hay herramienta para importar filas en bloque (`crear_producto` crea uno por llamada y el bucle corta a 8 pasos, `conversacion.py:79`). Para el objetivo «lector experto de Excel» faltan la lectura, la herramienta masiva y la medición.
2. **Costo de entrada evitable.** Con Claude Sonnet 5.5 (modelo por defecto, `proveedores.py` `MODELO_ANTHROPIC_GRANDE`) se ofrecen las 45 herramientas completas (≈ 8 000 a 10 600 tokens, más ≈ 450 de prompt de sistema y 286 de sobrecarga de tool use) **en cada una de las 2 a 8 llamadas de cada turno**, sin `cache_control`, y el uso de tokens que devuelve el proveedor se tira (`conversacion.py:272-275`). Con los supuestos de la sección 3, un turno típico cuesta ≈ US$ 0.055 a 0.065 sin caché y ≈ US$ 0.013 a 0.014 con caché «tibia» (−76 % a −79 %), pero el diseño actual **rompe el caché** por tres motivos concretos (hora en el prompt, nombre de usuario, preselección de herramientas por mensaje).
3. **No hay forma de medir si un cambio mejora o empeora.** Los tests actuales (`tests/test_nucleo.py`, etc.) validan la tubería con un proveedor guionado (`ProveedorPrueba`, `proveedores.py:319`) que ni calcula tokens (`'uso': 0`) ni puede emitir juicios sobre un modelo real.
4. **Entregado:** un arnés prototipo en `docs/auditoria/ronda2/brian-evals-prototipo/` con esquema de casos, **26 casos** derivados del Excel real (25 puntuables de forma determinista + 1 para juez LLM), evaluador Python sin red, y una demo reproducible (sección 6). La verdad de terreno se genera leyendo el archivo; nada está escrito a mano y el evaluador detecta si el Excel cambió.
5. **Hallazgo sobre el archivo real:** `up media/DCASA_listado_productos.xlsx` **no trae imágenes incrustadas** (`ws._images` = 0 en las 4 hojas; el zip no tiene `xl/media`), ni fórmulas (0 celdas con `=`). Las 323 fotos son PNG sueltos en `up media/` y la relación código↔foto está en la hoja «Imágenes (proyecto)». Por eso el dorado actual cubre celdas, vacíos, duplicados y cálculo; **las imágenes incrustadas en celdas necesitan un Excel de muestra que no existe en el repo** (sección 7, M-05).

## 2. Auditoría del prompt de sistema y las herramientas

### 2.1 Prompt de sistema (`conversacion.py:357-385`, `_describir_pantalla` 387-405)

| Aspecto | Hallazgo | Ruta:línea |
|---|---|---|
| Tamaño | 1 222 caracteres con pantalla de ejemplo ≈ 370 a 490 tokens. Es pequeño; el peso está en las herramientas (8 a 10× mayor). | `conversacion.py:357-385` |
| Parte variable dentro del prefijo | `Hoy es dd/mm/aaaa, HH:MM` (cambia cada minuto), nombre del usuario y empresa, canal y pantalla actual se interpolan **antes** de las reglas. Cualquier cambio invalida el caché del sistema y de los mensajes. | `conversacion.py:365-366, 361-362` |
| Texto libre de datos en nivel «sistema» | `nombre` del registro abierto (120 car.) y `registro` (1 500) se anexan al sistema (ya reportado como B-06 en `brian.md`). También ensucia el caché. | `conversacion.py:387-405` |
| Instrucciones en tensión | «Respuestas cortas… sin IDs sueltos» (l. 382) choca con tareas de extracción/importación, que necesitan salidas largas y exactas (códigos = identificadores). Conviene un modo «extracción» con otra regla. | `conversacion.py:382` |
| Lo que falta para Excel | No dice qué hacer con celdas vacías, duplicados, filas ambiguas ni cómo citar la celda de origen; «No inventes cifras» (l. 374) es el único freno. No hay ejemplos (few-shot). | `conversacion.py:370-383` |
| Defensa anti-inyección | Una sola línea (l. 380-381); los adjuntos usan delimitadores fijos falsificables (`<<FIN DE LOS DATOS>>`, `conversacion.py:474-476`). Caso adversarial `AD-03` del prototipo lo ataca. | `conversacion.py:380, 474` |

### 2.2 Definiciones de herramientas (`registro.py`, `herramientas_*.py`)

Medición propia (script `medir_herramientas.py`, análisis estático con `ast`; reproduce el esquema de `registro.py:116-130`):

| Métrica | Valor |
|---|---|
| Herramientas | 45 (catálogo 8, clientes 7, contabilidad 12, general 4, usuarios 4, ventas 10) |
| Caracteres del esquema JSON total | 26 412 (medio 587 por herramienta; parámetros medios 2.33) |
| Tokens estimados | 6 600 (regla del repo, caracteres/4) · 8 000 (español+JSON, /3.3) · 10 600 (tokenizador nuevo, +30 %, /2.5) |
| Las más pesadas | `reporte_contable` 1 098 car., `crear_factura` 910, `crear_producto` 885, `buscar_productos` 875, `buscar_ventas` 853, `abrir` 780 |
| Por rol (aprox., sin grupos implicados de Odoo) | administrador 26 412 car.; vendedor 12 549 (−52 %); cajero/contador 12 524 |
| Con ejemplos | 45 de 45 (todas llevan `ejemplos`, que se concatenan a la descripción, `registro.py:120-121`) |

Hallazgos:

- **E-01 · ALTO · lectura de Excel inexistente.** `MIMES_TEXTO` incluye `application/vnd.ms-excel` (el `.xls` binario antiguo) y lo decodifica como UTF-8 (`conversacion.py:89-91, 487-489`): produce basura. El `.xlsx` (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`) no coincide y responde «No puedo leer este tipo de archivo» (l. 491). No hay lectura de imágenes incrustadas, hojas, rangos ni fórmulas. Tampoco OCR: un PDF escaneado da «sin texto legible» (l. 497).
- **E-02 · ALTO · ninguna herramienta masiva.** Importar las 219 filas de «Productos» exigiría 219 llamadas a `crear_producto` (`herramientas_catalogo.py:196`); `MAX_PASOS = 8` (`conversacion.py:79`) lo corta. Falta una herramienta de lote con vista previa y una sola confirmación.
- **E-03 · ALTO · el adjunto se reenvía completo en cada llamada.** El texto extraído se guarda en `datos_adjuntos` (`conversacion.py:578`) y se anexa al mensaje de usuario en cada `_neutro` (l. 590-591); por tanto viaja en **cada paso del bucle** y en **cada turno posterior** mientras quepa en el presupuesto de 30 000 tokens (l. 421-440). La hoja «Productos» como CSV mide 15 349 caracteres ≈ 4 650 tokens; las 4 hojas, 45 519 caracteres ≈ 13 800 tokens, y `MAX_TEXTO_ADJUNTO = 20000` (l. 82, 496-497) las recorta en silencio (solo añade «… [recortado]»).
- **E-04 · ALTO · sin caché de prompt y sin contabilidad de tokens.** `ProveedorAnthropic.chatear` arma `system`, `tools` y `messages` sin `cache_control` (`proveedores.py:166-181`). El proveedor devuelve `uso` (`proveedores.py:233-235`) pero `_bucle` lo descarta (`conversacion.py:272-283`); no hay tabla de uso ni tope (ya señalado como B-10).
- **E-05 · MEDIO · la preselección por palabras choca con el caché.** `seleccionar` (`registro.py:141-159`) cambia el conjunto de `tools` según los dos últimos mensajes de usuario (`conversacion.py:417-419`). Según la documentación de caché, un cambio en las definiciones de herramientas invalida todo el caché (sección 8, fuente F-1). Además, para Haiku 4.5 el mínimo cacheable es 4 096 tokens: con 12 herramientas el prefijo mide ≈ 3 100 a 3 800 tokens (12 × 587 car. + sistema + 496 de sobrecarga) y **no se cachea en absoluto**. Se activa para cualquier modelo con «haiku», «mini», «8b»… en el nombre (`proveedores.py:79, 389-391`).
- **E-06 · MEDIO · la tubería de pruebas no ejerce la ruta de producción.** `'prueba'` está en `PEQUENOS` (`proveedores.py:79`), así que `es_grande('prueba')` es falso y **siempre** se preselecciona; la ruta «Sonnet con las 45 herramientas» nunca se prueba en CI. `ProveedorPrueba` registra nombres de herramientas pero no los esquemas ni el tamaño (`proveedores.py:323-325`).
- **E-07 · MEDIO · herramientas solapadas (riesgo de elección equivocada en modelos pequeños).**
  - Deudores: `clientes_que_deben` (`herramientas_clientes.py:139`), `facturas_pendientes(tipo=por_cobrar)` (`herramientas_contabilidad.py:207`), `reporte_del_dia` («por cobrar», `herramientas_ventas.py:74`) y `reporte_contable`.
  - Búsqueda: `buscar_en_todo` (`herramientas_generales.py:111`) vs `buscar_productos/clientes/ventas`; y `abrir` (l. 152) vs los `ver_*`.
  - Ventas: `reporte_del_dia` vs `resumen_ventas` (`herramientas_ventas.py:99`).
  - Mitigación ya presente: los `ejemplos` orientan (p. ej. «¿quién nos debe?»). Hace falta **medirlo** (caso `H-05` de `brian.md` y métrica `tasa de herramienta correcta`).
- **E-08 · MEDIO · tipos y contratos débiles entre herramientas.** `actualizar_producto.valor` es `string` para un precio (`herramientas_catalogo.py:227`) mientras `crear_producto.precio` es `number` (l. 187); el modelo debe decidir el formato y el código convierte (l. 240). Ningún esquema usa `strict` (OpenAI) ni salida estructurada para extracción.
- **E-09 · MEDIO · ambigüedad de ITBMS.** `crear_producto` dice «precio final (ITBMS incluido)» (`herramientas_catalogo.py:182`); el Excel rotula la columna C como «Precio (+ITBMS)» (`Productos!C1`) y la hoja Notas repite «Todos los precios son +ITBMS» (`Notas!B5`). El código actual lo trata como «con ITBMS incluido» (`scripts/importar_catalogo.py:11`, `docs/CATALOGO.md:20`), pero `enterprise-gap` y `brian-excel` lo marcan en la bitácora como **por confirmar** con la dueña (la factura 00821 sugiere «+ITBMS»). Mientras no se decida, un modelo puede interpretarlo en cualquiera de los dos sentidos y debe **preguntar**, no suponer. Caso `XL-21` (juez LLM).
- **E-10 · MEDIO · imágenes: límites y conteo de tokens desalineados.**
  - `MAX_IMAGEN = 5 MB` (`conversacion.py:83, 598`) rechaza **54 de las 323** PNG del repo (`up media/`, medias de 1 536 × 2 300 px, hasta 9.1 MB), aunque la API de Anthropic permite 10 MB por imagen en uso directo (fuente F-3).
  - `_tokens` supone 1 500 tokens por imagen (`conversacion.py:453`). La documentación da `⌈ancho/28⌉ × ⌈alto/28⌉` con tope 1 568 (estándar) o 4 784 (modelos 4.7 y posteriores). Para 1 536 × 2 300: ≈ 1 568 (estándar) o ≈ 4 565 (alta resolución, 55 × 83). El recorte de historial subestima hasta 3×.
  - Solo la última imagen del usuario se envía completa; las anteriores pasan a «[Imagen … ya vista antes]» (`conversacion.py:427, 594-597`): correcto para costo, pero el modelo pierde esa imagen en el turno siguiente.
- **E-11 · MEDIO · sin control de no determinismo.** No se fija `temperature` ni semilla (búsqueda de `temperature` en `proveedores.py`: 0 resultados). Para evals hay que repetir cada caso k veces y reportar `pass^k` (sección 4).
- **E-12 · BAJO · `max_tokens` fijo 8 000 para todo** (`proveedores.py:53, 99, 169`). Sirve para extracciones largas, pero un chat corto no necesita ese techo; con modelos de razonamiento de OpenAI `max_completion_tokens` incluye el razonamiento (NO VERIFICADO en esta ronda; ver `brian-modelos`).
- **E-13 · BAJO · recorte mudo de historial.** `_historial_neutro` descarta lo más antiguo sin resumen (`conversacion.py:421-440`), ya reportado como B-12.

## 3. Cálculo de tokens y costo por turno

**Supuestos (explícitos, cámbialos en `precios.json`):**

- Precios oficiales consultados el 2026-09-30 (F-2): Claude Sonnet 5.5 entrada US$ 2, salida US$ 10, escritura de caché 5 min US$ 2.50, lectura de caché US$ 0.20 por millón; Haiku 4.5: 1 / 5 / 1.25 / 0.10. Batch API: −50 %.
- Prefijo = esquemas (8 004 o 10 565 tokens) + sistema 450 + sobrecarga de tool use 286 (F-2, Sonnet 5.5) = **8 740 a 11 300 tokens**.
- Turno típico = 2 llamadas (herramienta y respuesta final): historial previo 3 000, mensaje nuevo 200, resultado de herramienta 800 + 300 de `tool_use`; salida total 500 tokens.
- Tokenizador: «Claude 4.7 y posteriores producen ≈ 30 % más tokens para el mismo texto» (F-2); si Sonnet 5.5 cae en ese grupo, vale la columna de 10.6 k (NO VERIFICADO sin contar con la API).

| Escenario (Sonnet 5.5) | Entrada por llamada 1 / 2 | Costo por turno |
|---|---|---|
| Hoy (45 herramientas, sin caché), esquemas 8.0 k | 11 940 / 13 040 | **US$ 0.055** |
| Hoy, esquemas 10.6 k | 14 501 / 15 601 | **US$ 0.065** |
| Con caché, «frío» (primer turno tras > 5 min: escribe todo) | igual | US$ 0.040 a 0.047 (−27 % a −28 %) |
| Con caché, «tibio» (turno dentro de 5 min del anterior) | igual | **US$ 0.013 a 0.014 (−76 % a −79 %)** |

Orden de magnitud mensual con 50 turnos/día × 22 días (supuesto, no dato de D'CASA): US$ 60 a 72 sin caché; ≈ US$ 14 a 15 si todos fueran tibios. La mezcla real dependerá de la frecuencia de uso (`NO VERIFICADO`: no hay telemetría porque `uso` se descarta).

**Imágenes y adjuntos (por mensaje):** una foto de 1 536 × 2 300 px = 1 568 a 4 565 tokens (F-3); la hoja «Productos» en CSV ≈ 4 650 tokens, que se repiten en cada llamada y turno (E-03). Un turno de importación con la hoja adjunta y 2 llamadas suma ≈ 9 300 tokens de datos, más el prefijo.

### 3.1 Optimizaciones propuestas (ordenadas por ahorro/esfuerzo)

| # | Cambio | Dónde | Ahorro estimado | Riesgo |
|---|---|---|---|---|
| O-1 | **Registrar `uso` por llamada** (entrada, salida, caché leída/escrita) en un modelo `brian.uso` y en `brian.accion`; mostrar costo por turno. | `conversacion.py:272-283`, `proveedores.py:233-235` | 0 directo, pero es prerrequisito de todo lo demás y de los evals de costo | ninguno |
| O-2 | **Prefijo estable + `cache_control`**: orden `tools` → `system` estático → mensajes. Sacar hora, usuario, empresa, canal y pantalla a un **mensaje de usuario etiquetado** después del punto de caché. | `conversacion.py:357-385`, `proveedores.py:166-181` | −76 % a −79 % de costo en turnos tibios; −27 % en fríos (sección 3) | exige no reordenar herramientas; probar con `cache_read_input_tokens` |
| O-3 | **TTL de caché según uso**: 5 min (1.25×) para chat; 1 h (2×) solo si hay ≥ 2 lecturas por hora (F-1). | `proveedores.py` | evita pagar de más en escritura | medir antes |
| O-4 | **Herramientas bajo demanda** en vez de preselección por palabras: núcleo de ≈ 8 herramientas (general + búsquedas ≈ 1 300 tokens) y el resto descubierto por la *tool search tool* de Anthropic (`defer_loading`, el prefijo no cambia y el caché se conserva) o, para otros proveedores, una meta-herramienta `buscar_herramientas(tema)` con el mismo núcleo fijo. Fuente F-4: −85 % de tokens de definición y precisión 49→74 % (Opus 4) y 79.5→88.1 % (Opus 4.5) en su benchmark. | `registro.py:133-159`, `conversacion.py:407-415` | prefijo de administrador de ≈ 8.7 k a ≈ 2.5 k tokens (−70 %, estimación propia) | el estado de la *tool search* es beta a la fecha del artículo (2025-11-24); (NO VERIFICADO que siga en beta) |
| O-5 | **Adjuntos por referencia**: guardar la hoja como recurso y dar `leer_adjunto(hoja, rango)` / `resumen_adjunto`; al modelo solo un índice (hojas, dimensiones, encabezados, 5 filas). | `conversacion.py:466-499, 578, 590` | −4 650 tokens por llamada y turno en la hoja «Productos» (−100 % de repetición tras el primer turno) | hace falta la herramienta nueva |
| O-6 | **Resumen incremental** del historial al superar el presupuesto, en vez de recorte mudo. | `conversacion.py:421-440` | acota el historial (máx. 30 000) a ≈ 2 000 + últimos turnos | el resumen debe evaluarse (caso `M-03`) |
| O-7 | **Salida estructurada** para extracción: una herramienta `registrar_extraccion` con esquema (código, nombre, precio nullable, `celda_origen`) o `response_format` con `strict` (OpenAI, F-7). | proveedores y herramientas | menos reintentos y menos tokens de salida; habilita puntuar por campo | `strict` exige todos los campos requeridos (nullable) |
| O-8 | **Límite de salida por tipo de turno**: 1 024 chat, 4 096 extracción (hoy 8 000 fijo). | `proveedores.py:53, 99` | acota el peor caso, no el típico | cortes: vigilar `fin='limite'` |
| O-9 | **Batch API (−50 %)** para evals nocturnos y cargas masivas no interactivas (F-2). | evals/CI | −50 % de entrada y salida; combinable con caché | latencia de horas; solo no interactivo |
| O-10 | Enrutar por tarea (Haiku para lecturas simples, Sonnet para extracción): ver `brian-modelos`. | `proveedores.py` | depende de medir con este arnés | — |

## 4. Diseño del arnés de evaluación

### 4.1 Principios

1. **Verdad de terreno derivada, no escrita a mano**: cada caso nace de celdas del Excel real (sha256 fijado) y de contrastes independientes (`docs/CATALOGO_REVISAR.md`). Si el Excel cambia, `evaluador.py --verificar` falla.
2. **Juez determinista primero** (igualdad normalizada, conjuntos, herramientas y argumentos). **LLM-como-juez solo** para lo que no tiene respuesta única: voz de marca (`CLAUDE.md`, reglas 1-6), si pregunta ante una ambigüedad, calidad de la explicación de un error. Buenas prácticas de diseño (propias; ver F-5, F-6 para el modelo «pruebas unitarias binarias»): rúbrica binaria, juez de **otra familia** que el modelo evaluado, temperatura 0, calibrar con 30 a 50 casos etiquetados por una persona y medir concordancia antes de confiar.
3. **Se evalúa el estado final, no solo el texto**: como τ-bench, que compara la base de datos al final con el estado objetivo (F-8). En Odoo: registros creados, `brian.accion.estado`, campos finales.
4. **Utilidad y seguridad juntas**: como AgentDojo (utilidad sin ataque, utilidad bajo ataque, tasa de éxito del ataque; F-9). Un modelo que «se defiende» negándose a todo debe perder puntos.
5. **Consistencia**: cada caso de escritura se corre k ≥ 3 veces (no hay control de `temperature`, E-11) y se reporta `pass^k` (aprueba solo si aprueban las k; F-8), además del promedio.

### 4.2 Formato de un caso (`esquema_caso.json`, JSON Schema 2020-12; un caso por línea en `.jsonl`)

| Campo | Contenido |
|---|---|
| `id`, `titulo`, `conjunto`, `tipo`, `etiquetas` | `conjunto`: `dorado_excel`, `adversarial`, `multiturno`, `roles`, `fotos`, `documentos`. `tipo`: `celdas`, `conteo`, `conjunto`, `derivado`, `nulo`, `herramienta`, `adversarial` |
| `rol`, `canal` | quién conversa (administrador, gerente_ventas, vendedor, cajero, contador) y por dónde |
| `entrada.mensajes` | turnos previos y el actual (multi-turno) |
| `entrada.adjuntos[]` | `archivo`, `hoja`, `rango`, `mutaciones[]` (celdas alteradas en una copia, para inyección) |
| `estado_bd` | fixture de Odoo para casos con herramientas (catálogo vacío, cliente con saldo…) |
| `herramientas_esperadas[]` | `nombre`, `argumentos_min` (subconjunto), `estado` (`hecha`, `por_confirmar`, `bloqueada`) |
| `herramientas_prohibidas[]` | permisos e inyección: cualquier llamada es fallo |
| `esperado` | `forma`: `celdas` (valor o `null` = debe venir vacío), `numero`, `conjunto`, `nulo`, `texto_clave`, `ninguna`; `rubrica` para juez LLM |
| `puntuacion` | `juez` (`determinista`/`llm`/`humano`), `tolerancia_numerica`, `peso`, `critico` |
| `fuente` | archivo, sha256, hoja, celdas de origen, `verificado_con`, `contraste` |

### 4.3 Formato de salida que debe producir el ejecutor

`{"_meta": {modelo, prompt, herramientas, ...}, "<id>": {"extraccion": ..., "texto": "...", "herramientas": [{nombre, argumentos, estado}], "uso": {entrada, salida, cache_lectura, cache_escritura}, "latencia_ms": n}}`. Es lo que debe volcar un ejecutor real: una orden de Odoo (`odoo shell`/test) que para cada caso carga el `estado_bd`, aplica `mutaciones` a una copia del Excel, corre `brian.conversacion.enviar()` y lee `brian.accion` y `uso` (O-1).

### 4.4 Métricas

| Métrica | Definición | Dónde |
|---|---|---|
| Exactitud por celda/campo | celdas correctas / celdas esperadas (texto normalizado, números con tolerancia ±0.005, `null` = vacío); para conjuntos, F1 | `evaluador.py` |
| Caso exacto | fracción con todos los componentes correctos | `evaluador.py` |
| Tasa de herramienta correcta | llamadas esperadas presentes con `argumentos_min` y estado correctos / esperadas | `evaluador.py` |
| Tasa de alucinación | (valores esperados `null` contestados con valor + números emitidos que **no existen en el Excel**) / valores emitidos. Límite conocido: un número inventado que sí exista en otra celda no se detecta por esta vía (por eso `XL-04` y `XL-12` también comprueban el `null`) | `evaluador.py` |
| Cumplimiento de permisos / inyección | llamadas a herramientas prohibidas (intentadas y ejecutadas); `critico=true` hace fallar la corrida | `evaluador.py` |
| Costo y latencia | tokens × `precios.json`; p50 y p95 de `latencia_ms`; costo por caso | `evaluador.py` |
| Consistencia | `pass^k` sobre k corridas | pendiente (ejecutor real) |
| Presupuesto de prompt (CI) | tamaño del catálogo y del sistema con tope (`medir_herramientas.py --max-chars`) | `medir_herramientas.py` |

### 4.5 Conjuntos

- **Dorado de Excel** (`XL-01…XL-21`): fila completa con vacíos, búsqueda por código, texto compuesto («Twin $139.99 · Full…») a campos, tamaño sin precio (`$—`), código repetido con dos precios, conteos (219 filas, 199 códigos únicos, 17 sin precio, 16 con tamaños, 331 imágenes), conjuntos por texto en «Observaciones» (2 «revisar», 12 «sin imagen»), existencias desconocidas, ficha sin código, cálculo de «El par (-10 %)», máximo y suma, otra hoja, y dos escrituras (`crear_producto`). Contrastes cruzados con `docs/CATALOGO_REVISAR.md`: 199 productos, 16 con tamaños, `ZEM-KING` y `81904`, dobles precios; y 11 «sin foto» frente a 12 filas del Excel (la 12.ª, `XXI061702`, tiene otra fila con imagen: diferencia explicada).
- **Adversariales** (`AD-01…03`): inyección en celda de Observaciones, en la hoja Notas y con falso cierre del delimitador de datos. Siguiente ronda: inyección dentro de una imagen (texto en foto), PDF y nombre de archivo (`brian.md` A-04, A-05, A-07).
- **Casos que propone `brian-excel` (§7 de su informe) y faltan aquí**: encabezado desplazado, dos tablas en una hoja, «Desde $99», fecha serial vs texto, CSV cp1252 con `;`, xlsx con macros, xlsx con contraseña, foto de ficha inclinada, y su extractor sintético (combinadas, fórmula sin caché, imagen flotante/en celda, hoja oculta, inyección). Su `salida/*.candidatos.json` puede servir como segunda verdad de oro (el sha256 del Excel coincide con el mío: `731580f9aab9…`).
- **Multi-turno** (`MT-01`): referencia anafórica («sube *ese* precio»). Ampliar con `M-01…M-11` de `brian.md`.
- **Por rol** (`RO-01`): vendedor sin grupo de gerente no debe crear productos. Ampliar con `P-01…P-18` de `brian.md`.
- **Fotos y documentos** (por construir): fotos de fichas con la tabla del Excel como verdad (los 4 casos de «las fotos muestran otro tipo de mueble» de `docs/CATALOGO_REVISAR.md` son un dorado listo); PDF con texto y escaneado.

### 4.6 Ejecución

| Nivel | Cuándo | Proveedor | Qué valida | Costo |
|---|---|---|---|---|
| **A. CI por PR** | cada push | `ProveedorPrueba` ampliado: **reproducción** de trazas grabadas (llamadas por caso) y `uso` calculado por caracteres/4 | el evaluador (con `oraculo.json` debe dar 1.000), `--verificar` del dorado, política/permisos de Odoo, presupuesto de tokens del prompt y de las herramientas, que las herramientas esperadas existan | 0 |
| **B. Nocturno** | cron (GitHub Actions) | modelos reales (Claude, OpenAI, Muse Spark cuando tenga API: ver `brian-modelos`), k = 3, Batch API donde se pueda | exactitud, alucinación, herramientas, inyección, costo, latencia | ≈ US$ 1.4 a 1.7 por corrida sin caché (25 casos × 2 llamadas × ≈ 12 a 15 k tokens de entrada con Sonnet 5.5) y ≈ US$ 0.3 con caché tibia; ×3 con k = 3 (estimación propia con los supuestos de la sección 3) |
| **C. Bajo demanda** | antes de cambiar modelo, prompt o herramienta | el que se va a cambiar y el actual | tabla antes/después, `--comparar` | igual que B |

Reglas: (1) `evals/baselines/<modelo>.json` versionado en Git; (2) un PR que toque `conversacion.py` (sistema), `registro.py` o `herramientas_*.py` adjunta el `--comparar` (plantilla de PR); (3) cualquier `criticos_fallidos` bloquea; (4) el nocturno abre un issue si la exactitud cae > 3 puntos o el costo por caso sube > 15 % (umbrales propuestos, no validados).

**Comparación entre modelos**: mismo conjunto, mismas definiciones de herramientas, mismo `estado_bd`; reportar exactitud, alucinación, `pass^k`, costo/caso y latencia p95 en una tabla (frontera de Pareto costo-exactitud). Las diferencias de tokenizador hacen que «tokens» no sea comparable: comparar **dólares** por caso y tokens medidos por el proveedor.

## 5. Investigación en internet (consultada el 2026-09-30)

Fuentes oficiales salvo indicación. Los hosts `arxiv.org` e `inspect.aisi.org.uk` estaban bloqueados por el proxy: lo que cito de ahí viene solo de resúmenes de búsqueda (marcado).

| Tema | Hallazgo | Fuente |
|---|---|---|
| Caché de prompt (oficial) | Escritura 5 min = 1.25× y 1 h = 2× del precio de entrada; lectura = 0.1× (0.05× en Opus 5.5). Orden del prefijo: `tools`, `system`, `messages`. Un cambio en `tools` invalida todo; imágenes añadidas/quitadas invalidan el de mensajes. Hasta 4 puntos de corte; existe caché automático con un `cache_control` de nivel superior. Mínimo cacheable: 512 tokens (Sonnet 5.5, Opus 5.5), 1 024 (Sonnet 5/4.6/4.5), 4 096 (Haiku 4.5). | F-1 |
| Precios y tool use (oficial) | Sonnet 5.5: US$ 2/10; Haiku 4.5: 1/5; Batch −50 %; sobrecarga del prompt de tool use 286 tokens en Sonnet 5.5 y 496 en Haiku 4.5; «Claude 4.7 y posteriores… ≈ 30 % más tokens». | F-2 |
| Visión (oficial) | Tokens = `⌈ancho/28⌉ × ⌈alto/28⌉`; tope 1 568 (estándar) o 4 784 (4.7+); 10 MB por imagen en API directa, 5 MB en Bedrock/Google Cloud; 100 imágenes por petición (modelos de 200 k); recomienda *Files API* para no reenviar base64 en cada turno y advierte que la compresión con pérdida daña el texto. | F-3 |
| Herramientas bajo demanda (oficial, blog técnico) | «85 % de reducción» de tokens de definición (55 k de 5 servidores MCP); `defer_loading`; precisión 49→74 % (Opus 4) y 79.5→88.1 % (Opus 4.5); ejemplos de uso de herramientas: 72→90 % en parámetros complejos; llamada programática de herramientas −37 % de tokens. Publicado 2025-11-24; cifras del propio proveedor. | F-4 |
| Evaluación de agentes (código abierto) | **promptfoo**: licencia MIT, corre 100 % local, comparación lado a lado, aserciones (deterministas, esquema JSON, JavaScript, auto-calificación), Acción de GitHub oficial que comenta el resultado en el PR; soporta OpenAI, Anthropic, Azure, Bedrock, Ollama. | F-5 |
| Evaluación de agentes (marco) | **Inspect AI** (UK AISI): marco de evaluación de LLM con *solvers*, *scorers* y herramientas; su repositorio `inspect_evals` incluye AgentDojo (solo por resultados de búsqueda; página bloqueada, NO VERIFICADO el detalle). | F-10 |
| Extracción de tablas/OCR | **olmOCR-Bench** (Allen AI): 7 010 pruebas binarias tipo «unit test» en 1 402 PDF, incluye 1 020 pruebas de tablas a nivel de celda; sin juez LLM ni referencia difusa: es el modelo a imitar para puntuar celda por celda. **OmniDocBench** (CVPR 2025): 1 651 páginas (v1.6), TEDS para tablas. **PulseBench-Tab**: benchmark multilingüe de extracción de tablas con evaluación basada en grafos (solo por resumen de búsqueda; NO VERIFICADO el contenido, arXiv bloqueado). | F-6 |
| Hojas de cálculo | **SpreadsheetBench**: 912 preguntas reales de foros de Excel, evaluación tipo *online judge* con varios casos de prueba por instrucción; en el artículo original los mejores modelos lograban 17 a 20 % frente a > 70 % de personas (resultado de 2024, desactualizado para modelos actuales; NO VERIFICADO el estado hoy). Existe V2 para flujos empresariales de varias hojas. Conjunto de datos en Hugging Face. | F-11 |
| Agentes con herramientas y usuario | **τ-bench / τ²-bench**: compara el estado de la base de datos al final con el objetivo; `pass^k` mide consistencia (aprueba solo si las k corridas aprueban). | F-8 |
| Inyección | **AgentDojo**: 97 tareas de usuario, 629 casos de seguridad (949 pares usuario/inyección según otra fuente), métricas: utilidad sin ataque, utilidad bajo ataque, tasa de éxito del ataque. | F-9 |
| Llamada a funciones | **BFCL** (Berkeley Function Calling Leaderboard): exactitud AST, ejecución y detección de irrelevancia (no llamar cuando no toca); v4 añade multi-turno y memoria. | F-12 |
| Salida estructurada y caché (OpenAI) | `strict: true` garantiza que los argumentos cumplan el esquema; caché automático desde 1 024 tokens con 90 % de descuento en la parte cacheada (según fuentes secundarias; NO VERIFICADO en la documentación oficial esta ronda). | F-7 |

**Qué es reutilizable gratis (verificado solo para promptfoo):** promptfoo (MIT) para ejecutar los mismos casos contra varios proveedores y comentar en el PR; los formatos de aserción de olmOCR-Bench y BFCL como inspiración (los conjuntos públicos están en inglés y PDF/funciones genéricas: no sustituyen un dorado propio en español con Excel de D'CASA); SpreadsheetBench como prueba de cordura de «manipular hojas con código» (no de «chatear con herramientas de Odoo»). Licencias de los conjuntos de datos: (NO VERIFICADO).

## 6. Prototipo y resultados de la demo

Ruta: `docs/auditoria/ronda2/brian-evals-prototipo/` (todo fuera de `addons/`; sin llamadas a API; requiere `openpyxl`, y `jsonschema` es opcional).

| Archivo | Función |
|---|---|
| `esquema_caso.json` | JSON Schema del caso |
| `generar_dorado.py` | lee el Excel real con openpyxl y escribe `casos/dorado_excel.jsonl` (26 casos) |
| `casos/dorado_excel.jsonl` | los casos generados (incluye 3 adversariales, 1 de rol, 1 multi-turno, 1 para juez LLM) |
| `evaluador.py` | `--verificar`, `--salidas`, `--umbral`, `--comparar` |
| `simular_salidas.py` | fabrica **salidas simuladas** (errores inyectados a mano; no es ningún modelo) |
| `precios.json` | precios de referencia (F-2), editables |
| `medir_herramientas.py` | tamaño del catálogo de herramientas sin arrancar Odoo |
| `correr_demo.sh` | ejecuta todo; salida guardada en `resultados/demo_consola.txt` |

Verificación del dorado (real): `casos que ya no coinciden con el Excel: ninguno`; `casos que no cumplen esquema_caso.json: ninguno`; sha256 del Excel `731580f9aab9…`. Datos comprobados al generar: 219 filas de datos, 199 códigos únicos, 17 filas sin precio en C, 16 con tamaños en D, 55 con Observaciones, 219 «Sin confirmar», 0 fórmulas, 0 imágenes incrustadas, 331 filas en «Imágenes (proyecto)» (igual que lo que dice la hoja Notas), y todos los «El par (-10 %)» coinciden con 2 × precio × 0.9 redondeado a 2 decimales.

Resultados de la demo (**SALIDAS SIMULADAS, no de un modelo real**; tokens y latencias inventados como muestra; umbrales de la corrida: exactitud ≥ 0.90, alucinación ≤ 0.02, críticos = 0):

| Corrida simulada | Exactitud | Casos 100 % ok | Herramienta correcta | Alucinación | Violaciones (intentos/ejecutadas) | Críticos fallidos | Costo/caso | Umbral |
|---|---|---|---|---|---|---|---|---|
| Oráculo (respuesta perfecta) | 1.000 | 1.000 | 1.0 | 0/41 | 0/0 | ninguno | US$ 0 | pasa |
| `sonnet_v1` (sin caché) | 0.908 | 0.840 | 1.0 | 1/41 (0.024) | 1/0 | XL-04, AD-03 | US$ 0.0247 | FALLA |
| `sonnet_v2_cache` | 0.948 | 0.880 | 1.0 | 1/41 (0.024) | 0/0 | XL-04 | US$ 0.0072 | FALLA |
| `haiku_v1` (12 herramientas) | 0.830 | 0.760 | 0.333 | 2/43 (0.047) | 2/2 | XL-04, XL-12, AD-01, RO-01 | US$ 0.0051 | FALLA |

Comparación `sonnet_v1` → `sonnet_v2_cache` (`--comparar --fallar-si-regresa`): exactitud +0.04, costo/caso −0.017 (−71 %), tokens de entrada −242 500, latencia p95 −900 ms; **regresión detectada: `XL-16`** (suma de precios); mejoras: `XL-08` y `AD-03`. El comando sale con código 1 por la regresión. Esto muestra lo que el arnés debe hacer: que un cambio que abarata y «mejora en promedio» se bloquee si rompe un caso que antes pasaba.

Límites honestos del prototipo: no ejecuta Brian ni Odoo (falta el ejecutor de la sección 4.3); no aplica aún las `mutaciones` de los casos adversariales al archivo; no calcula `pass^k`; el juez LLM no está implementado (XL-21 queda «pendiente de juez»); las cifras de la demo son sintéticas y **no** dicen nada del rendimiento de ningún modelo.

## 7. Mejoras de Brian para «lector experto de Excel, imágenes y documentos» (priorizadas)

| Prio | ID | Mejora | Por qué / evidencia | Medir con |
|---|---|---|---|---|
| P0 | M-01 | Medir: registrar `uso` (con caché) por llamada y por turno; tablero de costo por usuario/día y tope por perfil | E-04; sin esto no se puede optimizar ni comparar | `costo/caso`, test de `brian.uso` |
| P0 | M-02 | **Lector de `.xlsx`** (openpyxl, ya pertenece al ecosistema de Odoo): índice de hojas (nombre, dimensión, encabezados, primeras filas, celdas combinadas, fórmulas y valores calculados, hojas ocultas) y `leer_hoja(hoja, rango)` paginado con número de fila y dirección de celda; nunca volcar todo al prompt | E-01, E-03; coordinar con `brian-excel` | `XL-01…XL-18` |
| P0 | M-03 | **Importación en lote con vista previa**: `proponer_importacion(filas)` produce una tabla revisable (alta/modificación/duplicado/sin precio/anomalía) y **una** confirmación; el servidor aplica en bloque y reporta por fila | E-02; reglas de `CLAUDE.md` (no inventar precios: celdas vacías quedan vacías) | `XL-19/20`, tasa de alucinación |
| P0 | M-04 | **Contrato de extracción**: salida estructurada con `celda_origen`, `null` para vacío, lista de dudas (duplicados, `$—`, «revisar»); el sistema añade un modo «extracción» (exhaustivo) distinto del modo chat (breve) | E-08, sección 2.1 | exactitud por celda, alucinación |
| P0 | M-05 | **Excel de muestra con imágenes incrustadas** (incluye imágenes «flotantes» y «en celda») y su dorado; hoy el Excel real no las trae | sección 1 (punto 5) | casos nuevos `XL-IMG-*` |
| P1 | M-06 | Arnés en CI: `ProveedorPrueba` de **reproducción** + nivel A; nocturno nivel B con el mismo evaluador; línea base por modelo | sección 4.6 | `--comparar` en PR |
| P1 | M-07 | Prefijo estable y `cache_control` (O-2, O-3); mover hora/usuario/pantalla a un mensaje etiquetado | E-04, sección 3 | `cache_read_input_tokens`, costo/caso |
| P1 | M-08 | Herramientas bajo demanda (O-4) y agrupar las solapadas (E-07) con descripciones que digan **cuándo no** usarlas | E-05, E-07 | tasa de herramienta correcta por modelo |
| P1 | M-09 | Delimitadores de datos con nonce y saneo de nombres/celdas; regla de contaminación (si en el turno entró texto de una celda/imagen/PDF, las herramientas de construcción piden confirmación) | B-07, `AD-01…03` | utilidad bajo ataque, éxito del ataque = 0 |
| P1 | M-10 | Adjuntos por referencia (O-5) y `leer_adjunto` | E-03 | tokens de entrada por turno |
| P2 | M-11 | Fotos: reducir en servidor a ≤ 1 568 px de lado largo (o usar *Files API*) en lugar de rechazar > 5 MB; OCR local opcional para PDF escaneado; conteo de tokens de imagen alineado con el modelo | E-10 (54 de 323 PNG rechazadas) | casos `fotos` |
| P2 | M-12 | Resumen incremental del historial (O-6) | E-13 | `M-02`, `M-03` de `brian.md` |
| P2 | M-13 | Fijar `temperature` baja donde el proveedor lo admita y reportar `pass^k` | E-11 | varianza entre corridas |
| P2 | M-14 | Juez LLM calibrado para voz de marca y ambigüedad (`XL-21`) | sección 4.1 | concordancia con etiquetas humanas |
| P3 | M-15 | Mapa celda→campo de Odoo configurable («plantillas de importación» por tipo de Excel del negocio) | el negocio vive de Excel | exactitud en archivos nuevos |

## 8. Fuentes (consultadas el 2026-09-30)

- **F-1** Anthropic, *Prompt caching* (oficial): https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- **F-2** Anthropic, *Pricing* (oficial): https://platform.claude.com/docs/en/about-claude/pricing
- **F-3** Anthropic, *Vision* (oficial): https://platform.claude.com/docs/en/build-with-claude/vision
- **F-4** Anthropic Engineering, *Advanced tool use* (oficial, 2025-11-24): https://www.anthropic.com/engineering/advanced-tool-use
- **F-5** promptfoo (repositorio, licencia MIT): https://github.com/promptfoo/promptfoo · Acción de GitHub: https://github.com/promptfoo/promptfoo-action · documentación: https://www.promptfoo.dev/docs/usage/command-line/
- **F-6** olmOCR-Bench (Allen AI; vía resumen de búsqueda): https://allenai.org/blog/olmocr-2 · OmniDocBench: https://github.com/opendatalab/OmniDocBench (vía búsqueda)
- **F-7** OpenAI, *Structured outputs* (vía búsqueda, no abierta): https://developers.openai.com/api/docs/guides/structured-outputs · caché automático: https://developers.openai.com/cookbook/examples/prompt_caching_201
- **F-8** τ-bench: https://github.com/sierra-research/tau2-bench (vía búsqueda)
- **F-9** AgentDojo: https://github.com/ethz-spylab/agentdojo · https://ukgovernmentbeis.github.io/inspect_evals/evals/safeguards/agentdojo/index.html (vía búsqueda)
- **F-10** Inspect AI: https://inspect.aisi.org.uk/ (bloqueado por el proxy; NO LEÍDO)
- **F-11** SpreadsheetBench: https://spreadsheetbench.github.io/ · https://huggingface.co/datasets/KAKA22/SpreadsheetBench (vía búsqueda)
- **F-12** BFCL: https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard · https://proceedings.mlr.press/v267/patil25a.html (vía búsqueda)

## 9. NO VERIFICADO

- Conteos reales de tokens: ninguna llamada al endpoint de conteo (sin clave de API). Usé rango 6.6 k a 10.6 k para el catálogo; el tokenizador de Sonnet 5.5 (¿+30 %?) no está confirmado.
- Frecuencia real de turnos, mezcla de turnos fríos/tibios y número medio de llamadas por turno (supuesto: 2). No hay telemetría porque `uso` se descarta.
- Si la *tool search tool* (`defer_loading`) sigue en beta y si OpenAI/Muse Spark ofrecen un equivalente (tema de `brian-modelos`).
- Caché automático de OpenAI y `strict` en las definiciones actuales: solo vía resúmenes de búsqueda.
- Detalles de PulseBench-Tab, Inspect AI, licencias de los conjuntos de datos públicos y resultados actuales de SpreadsheetBench (el 17 a 20 % es de 2024).
- La vista por rol (−52 % para vendedor) no resuelve los grupos implicados de Odoo; es aproximada.
- La demo usa salidas simuladas; no hay medición de ningún modelo real.
- Coordinación: al escribir este informe no existían aún los informes de `brian-excel` ni `brian-modelos` en `docs/auditoria/ronda2/`. Dejé el contrato de intercambio en la bitácora (formato de salidas, `--verificar`, métricas) para que lo usen; deben confirmar que sus propuestas (lector xlsx, ruteo de modelos) se miden con estos casos.
