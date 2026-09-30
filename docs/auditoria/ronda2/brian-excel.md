# brian-excel (ronda 2): Brian leyendo Excel, fotos y documentos

Fecha: 2026-09-30. Agente: `brian-excel`. Solo lectura sobre `addons/`; el prototipo vive en
`docs/auditoria/ronda2/brian-excel-prototipo/` (no toca `addons/`).

## 1. Resumen

1. **Hoy Brian NO lee Excel.** Un `.xlsx` adjunto responde «No puedo leer este tipo de archivo»
   (`conversacion.py:491`). El único «Excel» que admite es `application/vnd.ms-excel` (`.xls` binario
   viejo) y lo hace mal: lo decodifica como UTF-8 (`conversacion.py:88-89,487-489`) y entrega basura.
   Word (`.docx`) tampoco. Sí lee: PDF (texto nativo, sin OCR), CSV/TXT/JSON/MD e imágenes (visión).
2. **El Excel real del negocio es más simple de lo que se temía, pero engañoso**: 4 hojas, 0 celdas
   combinadas, 0 fórmulas, 0 imágenes incrustadas, 0 comentarios, 0 hojas ocultas (medido). Es un
   archivo **generado por script** desde Canva (`Notas!B2:B4`), no una planilla hecha a mano. Las
   fotos están **fuera** del Excel: 323 PNG en `up media/` (1.536 px de ancho; cada PNG es una
   «página Canva» completa, no una foto de producto). La dificultad real es de **semántica**: precios
   en texto («Twin $139.99 · Full $170.99 …»), duplicados con precio distinto, códigos con `/`,
   encabezado «+ITBMS», y cruce código↔nombre de archivo.
3. **El importador actual (`scripts/importar_catalogo.py`) funciona pero es un script de una sola
   vez**: columnas por posición fija (`importar_catalogo.py:155`), sin validación de encabezados,
   sin vista previa, y no detecta cambios de formato. No sirve como base de una herramienta de Brian.
4. **Diseño propuesto**: extracción determinista primero (openpyxl + XML crudo, sin modelo), esquema
   intermedio JSON celda→valor/fórmula/imagen, interpretación determinista de lo regular (regex de
   precios por tamaño), modelo solo para lo ambiguo (encabezados irregulares, fichas-imagen, PDFs
   escaneados), salida validada contra esquema, **vista previa + confirmación humana**, idempotencia
   por hash, trazabilidad fila→registro y reversión por lote. Las herramientas nuevas son
   `leer_archivo`, `proponer_importacion` (lectura) y `aplicar_importacion` (**sensible**).
5. **Prototipo funcionando** (8 pruebas verdes): extrae el Excel real en 0,3 s a un JSON intermedio,
   detecta los 6 códigos con precios contradictorios, 11 sin foto, 2 precios por tamaño no crecientes,
   y resuelve imágenes flotantes y «en celda» (richData) en un archivo sintético.
6. **Hallazgo transversal**: el mismo Excel dice «Precio (+ITBMS)» y `Notas!B5` «Todos los precios son
   +ITBMS»; `catalogo.py` y `docs/CATALOGO.md` los cargan como «ITBMS incluido». Ya está en la
   bitácora (enterprise-gap, sitio-web). **Brian no debe importar precios hasta que el dueño lo confirme**;
   la herramienta nueva debe exigir ese parámetro explícito (`modo_itbms`), nunca suponerlo.

## 2. Qué hace Brian hoy con adjuntos (con ruta:línea)

| Tema | Hoy | Evidencia |
|---|---|---|
| Subida en el panel | Hasta 15 MB por archivo, cualquier tipo; se guarda como `ir.attachment` | `static/src/js/brian_panel.js:22,466` |
| Subida en Telegram | Hasta 10 MB; foto (la mayor) o documento | `models/telegram.py:45,188-204,382-402` |
| MCP | No hay canal de archivos: solo JSON-RPC de 1 MB (`mcp.py`) | `docs/BRIAN.md` «Límites» |
| Validación de dueño | Solo adjuntos propios o de la conversación | `conversacion.py:459-464` |
| PDF | Texto nativo con `PdfFileReader.extract_text()`; sin OCR ni imágenes; escaneado → «(El archivo no tiene texto legible.)» | `conversacion.py:483-486,495` |
| CSV/TXT/JSON/MD | Decodifica UTF-8 con `errors='replace'` (Excel en español a menudo guarda CSV en cp1252/`;`: se corrompe) | `conversacion.py:487-489` |
| **XLSX** | **No soportado**: mimetype `…spreadsheetml.sheet` no está en `MIMES_TEXTO` y la extensión `.xlsx` no está en la lista | `conversacion.py:88-89,487-491` |
| **XLS** | Entra por `application/vnd.ms-excel` y se decodifica como texto: basura binaria que además gasta tokens | `conversacion.py:88-89,487` |
| **DOCX** | No soportado | `conversacion.py:491` |
| Imágenes | Solo el **último** mensaje de usuario lleva las imágenes; las anteriores quedan como «[Imagen … (ya vista antes)]» (el modelo ya no las ve) | `conversacion.py:427,594-595` |
| Límite de imagen | 5 MB (archivo crudo) → si pasa, nota «demasiado grande» y **no se redimensiona** | `conversacion.py:83,598-599` |
| Formato de imagen | Se reenvía el mimetype tal cual; sin conversión a JPEG/WebP ni validación de que sea png/jpeg/gif/webp (HEIC de iPhone → error del proveedor) | `conversacion.py:601-602`, `proveedores.py:195-197` |
| Texto extraído | Máx. 20.000 caracteres por adjunto, corte mudo al final («… [recortado]») | `conversacion.py:82,496-497` |
| Costo de imágenes | Se estima 1.500 tokens por imagen fija | `conversacion.py:452` |
| Reenvío | `datos_adjuntos` y las imágenes se guardan en el mensaje y se reenvían en cada paso del bucle (B-12) | `conversacion.py:204,590-607` |
| Marcado como dato | Texto de adjuntos entre `<<DATOS … >>` … `<<FIN DE LOS DATOS>>` (delimitador fijo, falsificable: A-04 de `brian.md`) | `conversacion.py:473-477` |
| Proveedores sin visión | Imagen se descarta con nota; sin OCR alternativo | `conversacion.py:596-597`, `proveedores.py:262-268` |
| Escritura | Solo `crear_producto` (uno a uno): sin creación por lote, sin vista previa, sin reversión | `herramientas_catalogo.py:196-231` |

**Qué se pierde al convertir un Excel a texto hoy** (aunque se arreglara el mimetype pegando el
binario en `decode`): todo. Con un lector ingenuo de texto se pierden: imágenes flotantes e
incrustadas en celda, el **ancla** imagen→celda/fila, celdas combinadas (solo la celda superior
izquierda tiene valor), fórmulas frente a valores (openpyxl con `data_only=True` devuelve `None` si el
archivo nunca se calculó en Excel; con `False` no da el valor), formatos de número y fecha
(`0.00`, `dd/mm`, moneda), hojas y filas ocultas, comentarios/notas, hipervínculos, nombres definidos,
validaciones y filtros. El Excel real tiene 4 hojas (`Notas` explica el origen); leer solo la
primera pierde el contexto.

## 3. El Excel real como caso de prueba (medido con Python real)

Archivo `up media/DCASA_listado_productos.xlsx` (40.224 bytes, sha256 `731580f9…`), openpyxl 3.0.9.
Reproducible: `python3 extractor.py "up media/DCASA_listado_productos.xlsx" --salida salida --fotos "up media"`.

| Medida | Resultado |
|---|---|
| Partes del zip | `sheet1..4.xml`, `sharedStrings`, `styles`, `theme`. **No hay** `xl/drawings`, `xl/media`, `xl/richData`, `comments`, `externalLinks`, `vbaProject` |
| Hojas (todas visibles) | `Productos` A1:G220 · `Imágenes (proyecto)` A1:D332 · `Todas las fichas` A1:G253 · `Notas` A1:B9 |
| Imágenes incrustadas (flotantes o en celda) | **0** en las 4 hojas |
| Celdas combinadas | **0** |
| Fórmulas | **0** (las 1.000+1.328+1.338+18 celdas con dato son constantes) |
| Comentarios / filas y columnas ocultas / validaciones / formato condicional | 0 / 0 / 0 / 0 |
| Congelado y filtro | `A2` y autofiltro en las 4 hojas |
| Hoja `Productos` | 219 filas de datos, **199 códigos únicos** (20 filas repetidas: 14 idénticas, 6 con precio distinto) |
| Precio único (col. C) | 202 filas (float); 17 vacías |
| «Precios por tamaño» (col. D, texto) | 16 filas; ejemplo `Twin $139.99 · Full $170.99 · Queen $216.99 · King $341.99`; 1 con `Queen $—`; dos con orden no creciente (Queen > King y King < Queen) |
| «Combo / el par» (col. E, texto) | 63 filas: 33 «Combo con colchón $X», 17 «El par (-10%) $X», 13 listas de tamaños |
| Stock (col. F) | 219 de 219 = «Sin confirmar» |
| Observaciones (col. G) | 55 con texto (39 «Mismo código aparece con otro precio/versión», 11 «Ficha sin imagen…») |
| Códigos | 12 con minúsculas (`clb0119018`, `up001`, `orlando`, `hd`…), 3 con `/` (`YMO-001/03`, `1062010734/5/6N`, `1062010751/2/3/4N`) |
| Encabezado de precio | «Precio (+ITBMS)» / «Precios por tamaño (+ITBMS)»; `Notas!B5`: «Todos los precios son +ITBMS» |
| `Todas las fichas` | 252 fichas en 6 diseños Canva (`NUEVOS PRODUCTOS` 100, `INVENT. D´CASA` 86, `PRODUCTOS NUEVOS` 47, `NEW FORMAT` 11, `COLCHONES` 5, `SOFÁS` 3); aquí el precio es **texto** con `$` (`'Twin $104.99'`), a diferencia de `Productos` donde es número |
| `Imágenes (proyecto)` | 331 filas (página→archivo→código) frente a **323 PNG** en disco: 8 nombres de la hoja no existen como archivo (`HYI220725_1`, `HYI220725_3`, `LXI062903_2`, `LXI071006_1`, `XXI061701_1`, `ZQ063605_1`, `ZQ063606_1`, `ZQ063609_1`); 0 PNG sin fila |
| Códigos sin ningún PNG | 11 (coincide con «Ficha sin imagen»: el prototipo los marca `sin_foto_en_carpeta`) |
| PNG | 323 archivos, 993 MB total, mediana 2,7 MB, máximo 9,07 MB; dimensiones típicas 1536×2761 (97), 1536×1536 (44)… Cada PNG es una **página Canva entera** (con texto y precio impresos) |

### Consecuencias para Brian

* **Límites de imagen con este archivo**: 54 de 323 PNG superan 5 MB crudos (`MAX_IMAGEN`,
  `conversacion.py:83`) y 11 superan ~7,5 MB, que en base64 pasan los 10 MB que admite la API de
  Anthropic (fuente §6). Hoy, esas 54 imágenes serían rechazadas por Brian («demasiado grande»).
  Hay que redimensionar/convertir a JPEG **antes** de enviar, no rechazar.
* **Costo de visión** (calculado con la fórmula oficial ⌈ancho/28⌉×⌈alto/28⌉ y topes por nivel, §6):
  una página 1536×2761 cuesta ≈1.568 tokens visuales en nivel estándar (tope del nivel) y ≈4.784 en
  nivel de alta resolución (Claude 4.7 y posteriores). Las 323 páginas: ≈0,5 M tokens (estándar) a
  ≈1,5 M tokens (alta). Precios: los calcula `brian-modelos`; no los cito aquí.
* **Releer las fichas con visión NO es necesario para el 100 %**: el Excel ya trae código, nombre y
  precios; la visión solo sirve para lo que el Excel no dice (medidas impresas, descriptor, portada,
  foto de otro tipo de mueble). Esas fichas ya se revisaron a mano en `fichas.json` (CATALOGO.md).
  Ahí el modelo aporta verificación, no extracción.
* **Cómo lo leyó `importar_catalogo.py`**: `load_workbook(data_only=True)` (`:148`), hoja
  `Productos` por nombre fijo y 7 columnas desempaquetadas por posición (`:149,:155`); precios por
  tamaño con regex `Twin|Full|Queen|King` + `$` (`:65-78`); duplicados: gana la primera fila y se
  anota (`:162-170`); fotos por nombre de archivo = código (`:91-101`); no lee `Todas las fichas` ni
  `Imágenes (proyecto)` ni `Notas`. Bien hecho: no inventa, anota lo dudoso en `CATALOGO_REVISAR.md`.
  Frágil: si el dueño agrega una columna o cambia el orden, desempaqueta mal **sin avisar**; los
  tamaños solo `Twin|Full|Queen|King` (un «Individual/Matrimonial» se descartaría en silencio);
  `precio()` toma el primer `$x.xx` del texto, así que «El par (-10%) $X» o dos precios en una celda
  se leen como uno.
* **Qué habría que hacer para que Brian lo lea solo**: (a) soportar `.xlsx` (hoy no); (b) mapear
  columnas por encabezado con confianza y pedir confirmación si <1; (c) tratar `Productos` + `Todas las
  fichas` + `Imágenes (proyecto)` como una sola fuente relacional (código = llave); (d) cruzar con
  la carpeta de fotos o un zip; (e) emitir las mismas alertas que hoy da `CATALOGO_REVISAR.md` como
  parte de la vista previa, no como archivo aparte; (f) exigir el `modo_itbms`.

## 4. Diseño de la canalización de ingesta

```
adjunto ──> 0 detectar ──> 1 extraer (determinista) ──> 2 normalizar ──> 3 interpretar ──> 4 validar
 (xlsx/csv/         tipo por      openpyxl + XML crudo:     tabla(s),        regex primero;   esquema JSON,
  pdf/docx/foto)    firma, no     celdas→valor/fórmula/     encabezado,      modelo solo      reglas de
                    por mimetype  imagen/combinada/         tipos            si confianza<1   negocio,
                                  comentario/oculta                          o es imagen/PDF  duplicados
                                                                                               │
       8 revertir  <── 7 aplicar (lote, savepoint, idempotente) <── 6 confirmar (humano) <── 5 vista previa
```

**0. Detección.** Por firma de bytes, no por `mimetype` del navegador (que a menudo viene vacío o
`application/octet-stream`): zip con `xl/workbook.xml` = xlsx; `%PDF` = PDF; zip con `word/document.xml` =
docx; `\xD0\xCF\x11\xE0` = OLE (xls/doc viejo: pedir guardar como xlsx o convertir con LibreOffice);
PNG/JPEG/WebP/GIF/HEIC por cabecera. Defensa antes de abrir: tamaño descomprimido ≤200 MB, razón
≤100×, sin rutas `..`, macros y vínculos externos **no se ejecutan ni se siguen** (implementado en
`extractor.revisar_zip`). openpyxl por defecto no protege contra XML bombs; usar `defusedxml` (fuente §6).

**1. Extracción determinista** (sin modelo; implementada en el prototipo):
valor y fórmula (libro abierto dos veces: `data_only=False/True`; fórmula sin caché = riesgo),
formato de número, celdas combinadas (propaga el rango), comentarios, hipervínculos, hojas/filas/
columnas ocultas, nombres definidos, filtros, validaciones, **imágenes flotantes** (XML de `drawing`:
ancla `oneCell/twoCell/absolute` → celda de origen, sha256, tamaño, formato) e **imágenes en celda**
(cadena `vm` → `metadata.xml` → `rdrichvalue.xml` → `richValueRel.xml` → `media`, que openpyxl no
ve; fuente §6). Las imágenes se guardan por hash (deduplicación) y se referencian por celda.

**2. Esquema intermedio** (`dcasa.xlsx/1`, ver `salida/*.intermedio.json`): por hoja, `estado`,
`dimension`, `combinadas[]`, `filas_ocultas[]`, `imagenes[{tipo, celda|celda_desde, sha256, ancho, alto}]`
y `celdas{"B4": {valor, formula?, formato?, combinada_en?, imagenes?, comentario?, enlace?,
sospecha_instruccion?}}`. Es la **única** representación que ve el modelo (nunca el binario del xlsx).
Para el modelo se comprime (idea de SheetCompressor, §6): encabezados + 5-10 filas de muestra +
resumen de columnas (tipo, únicos, vacíos), no las 219 filas; el resto lo procesa código.

**3. Interpretar: código primero, modelo después.**
* Determinista: detectar la fila de encabezado y mapear columnas por palabras clave (con el orden
  correcto: «Precio por tamaño» también casa con «precio», bug real que el prototipo corrigió);
  `precios_por_tamano()` con regex; códigos normalizados; alertas (sin precio, tamaño sin precio,
  precios no crecientes, código en minúsculas, duplicado idéntico/contradictorio, sin foto).
* Modelo **solo** si `confianza_mapa<1` (columna sin mapear), o texto libre que la regex no entiende
  («Desde $99, 2×1 en fin de mes»), o la fuente es imagen/PDF escaneado (visión/OCR), o foto de
  ficha para extraer medidas. Modelo barato primero; escalar al grande si la validación falla (ruteo:
  `brian-modelos`). El modelo devuelve JSON con esquema (`tool_use` forzado / salida estructurada), y
  **cada campo trae `celda_origen`** para verificar que el dato exista en el intermedio (un valor que no
  está en la celda citada se descarta: anti-alucinación).

**4. Validar.** Esquema JSON estricto (tipos, `enum` de tamaños, rangos de precio; ver B-16: hoy
`registro.py` no valida tipos) + reglas de negocio: «no inventar precios» (todo precio debe aparecer
literal en una celda), código único, `modo_itbms` explícito, categoría ∈ catálogo, sin duplicado
contra Odoo (`default_code` y similitud de nombre), fotos existentes.

**5. Vista previa.** Tabla compacta en chat/Telegram: N nuevos, N actualizaciones (antes→después),
N omitidos, N con alertas (las 6 discrepancias de precio primero). Se guarda como `brian.importacion`
(estado `borrador`) con su JSON, el hash del archivo y el `accion_id`. Sin `sudo`: corre con los
permisos del usuario.

**6. Confirmación humana.** `aplicar_importacion` es **sensible** (mismo mecanismo de `brian.accion`
por confirmar, con tarjeta que lista valores reales: B-09). Desde MCP nunca se ejecuta. Caducidad de
la tarjeta (B-08). Cambios de precio > umbral exigen segunda confirmación (B-18).

**7. Aplicar.** Por lotes (p. ej. 50 filas) con `savepoint` por lote; si uno falla, el resto continúa
y se reporta. **Idempotencia**: llave `(sha256 del archivo, hoja, fila)` → `brian.importacion.linea`;
reenviar el mismo archivo no duplica. Un archivo nuevo con mismos códigos = actualización solo de
campos cambiados. **Trazabilidad fila→registro**: cada línea guarda `hoja!A17 → product.template#id`,
y el producto conserva `dcasa_origen` (archivo + hash + celda).

**8. Reversibilidad.** Cada línea guarda los valores previos de los campos tocados; `deshacer_importacion`
(sensible) restaura creaciones (archiva, no borra: política de Brian) y valores anteriores; solo si el
registro no cambió después (compara `write_date`). El libro de puntos y la contabilidad quedan fuera.

**Archivos grandes.** Lectura en streaming (`openpyxl read_only=True` o `python-calamine`, más rápido pero
sin imágenes ni comentarios); límites: hoja >5.000 filas o >5 MB de intermedio → se procesa por partes
de N filas con el mismo encabezado; las imágenes se suben a la Files API de Anthropic o se miniaturizan
(máx. 1.568 px de lado largo en nivel estándar) antes de pasarlas al modelo; en el contenedor sin
disco persistente (CLAUDE.md) el archivo original vive en `ir.attachment` (BD) y el procesamiento en
memoria/`/tmp`. La extracción pesada no debe correr dentro de la transacción que espera al LLM (B-11):
va en un trabajo aparte (cola/cron de `brian-eventos`).

**PDF y Word.** PDF con texto → texto nativo + tablas con `pdfplumber`/Docling (local, MIT) y solo
las páginas dudosas a visión; PDF escaneado → páginas como imagen al modelo con visión (Claude procesa
cada página como texto + imagen; ≈1.500-3.000 tokens/página de texto más el costo de imagen, §6) o OCR
local; Word → `python-docx` para texto y tablas y para imágenes convertir a PDF (recomendación oficial
de Anthropic para `.docx` con imágenes, §6). Límite Claude: 32 MB y 600 páginas por petición (100 si
el contexto <1 M tokens): trocear.

## 5. Herramientas nuevas propuestas

Convenciones de `registro.py` (verbo + objeto en español, pocos parámetros, nivel y grupos).
Todas corren **como el usuario**; grupos = `GERENTE_VENTAS` para catálogo (como `crear_producto`).

| Herramienta | Parámetros | Devuelve | Nivel | Notas |
|---|---|---|---|---|
| `leer_archivo` | `adjunto` (id o nombre), `hoja?` (texto), `rango?` (p. ej. `A1:G40`), `max_filas?` (def. 40) | Resumen por hojas (ocultas marcadas), encabezados detectados, muestra, conteo de combinadas/fórmulas/imágenes, alertas. Todo marcado como DATO | lectura | Reemplaza el `decode` de hoy; acepta xlsx/csv/pdf/docx; paginable |
| `ver_imagen_de_celda` | `adjunto`, `celda` | Imagen (miniatura JPEG ≤1.568 px) ligada a esa celda/fila | lectura | Para fichas con foto incrustada |
| `proponer_importacion_catalogo` | `adjunto`, `hoja`, `modo_itbms` (`incluido`/`mas_itbms`, **obligatorio**), `mapa_columnas?`, `fotos_adjunto?` | `importacion_id` + vista previa (nuevos/cambios/omitidos/alertas) | lectura (escribe solo el borrador) | Nunca toca `product.template`; pide `mapa_columnas` si confianza <1 |
| `aplicar_importacion` | `importacion_id`, `solo_lineas?` (lista), `excluir_alertas?` (bool, def. true) | Conteo creados/actualizados/omitidos y `importacion_id` | **sensible** | Confirmación humana con valores reales; idempotente; lotes con savepoint; MCP nunca |
| `deshacer_importacion` | `importacion_id`, `motivo` | Qué se revirtió y qué no (por cambios posteriores) | **sensible** | Archiva creaciones, restaura valores previos; motivo obligatorio |
| `comparar_con_excel` | `adjunto`, `hoja` | Diferencias Odoo vs Excel (precio, nombre, faltantes) | lectura | Sin escribir; sirve para auditar |
| `importar_clientes_xlsx` (fase 2) | igual patrón | Ídem | sensible | Reutiliza `_b_duplicado_celular` (llave = celular); RUC/teléfonos: aviso de privacidad (S-10) |

Permisos extra: sin grupo `sales_team.group_sale_manager`, solo `leer_archivo`. `aplicar_importacion`
rechaza si hay `sospecha_instruccion` en las celdas usadas o si el turno está contaminado por texto no
confiable sin confirmación (regla B-07c). Límite de filas por aplicación (p. ej. 500) y de importaciones
por hora (política). Registro en `brian.accion` con `importacion_id` y hash del archivo.

## 6. Fuentes (consultadas 2026-09-30)

Oficiales (proveedor / proyecto):

1. Claude, Vision: https://platform.claude.com/docs/en/build-with-claude/vision — imágenes por
   petición (API: 100 si ventana 200k, 600 otros; claude.ai: 20); máx. 8000×8000 px; **si hay >20
   imágenes, tope de 2000 px por lado**; **10 MB por imagen (base64) en API directa, 5 MB en Bedrock y
   Google Cloud**; formatos JPEG/PNG/GIF/WebP; costo ⌈ancho/28⌉×⌈alto/28⌉; nivel estándar tope 1.568 px /
   1.568 tokens; alta resolución (Claude 4.7+) 2.576 px / 4.784 tokens; petición máx. 32 MB; Files API
   (`file_id`) para no reenviar base64 en cada turno.
2. Claude, PDF support: https://platform.claude.com/docs/en/build-with-claude/pdf-support — 32 MB y 600
   páginas por petición (100 si el contexto es <1 M); cada página se convierte en imagen **y** se extrae su
   texto; ≈1.500-3.000 tokens de texto por página más costo de imagen; PDF sin contraseña; dividir los
   densos.
3. Claude, Files API: https://platform.claude.com/docs/en/build-with-claude/files — 500 MB por archivo, 1 TB
   por organización; `.docx`/`.xlsx` **no** son bloques `document`: convertir a texto o PDF (`.docx` con
   imágenes → PDF); las operaciones de archivos son gratis (el contenido se cobra como entrada); los
   archivos son visibles para todo el workspace (no aceptar `file_id` de usuarios).
4. openpyxl (PyPI): https://pypi.org/project/openpyxl/ — 3.1.5 (2024-06-28), MIT; **no protege de
   «billion laughs»/cuadrática salvo con `defusedxml`**; imágenes y gráficos pueden perderse al
   cargar y guardar. (La doc en readthedocs está bloqueada por el proxy; ver NO VERIFICADO.)
5. Microsoft, MS-XLSX Rich Value Data: https://learn.microsoft.com/en-us/openspecs/office_standards/ms-xlsx/896934fd-8df7-43f4-b154-2d39371c270d
   (aparece en la búsqueda; **no abrí la página**, solo el resumen del buscador).
6. Microsoft MarkItDown (GitHub, MIT): https://github.com/microsoft/markitdown — convierte PDF, Word,
   Excel, imágenes (EXIF/OCR) a Markdown; «pensado para análisis por LLM, no para fidelidad de
   presentación»; aviso de seguridad (corre con los privilegios del proceso). Detalle de cómo lee xlsx: no
   documentado en el README.
7. Docling (IBM, MIT): https://docling.org/ y https://arxiv.org/html/2408.09869v5 — PDF/DOCX/PPTX/XLSX/imágenes
   → Markdown/JSON; análisis de maquetación (DocLayNet) y estructura de tablas (TableFormer); corre local.

Blogs / issues / papers (no oficiales):

8. Incidencia sobre imágenes «Colocar en celda» y cadena richData:
   https://github.com/yfedoseev/office_oxide/issues/302 — celda `t="e" vm="N"` con `#VALUE!` como reserva;
   cadena `metadata.xml` → `richData/rdrichvalue.xml` → `richValueRel.xml` → `media/`. Corroborada por
   búsqueda: https://github.com/abap2xlsx/abap2xlsx/issues/1366 (no abierta).
9. SpreadsheetLLM (Microsoft, arXiv 2407.09025): https://arxiv.org/abs/2407.09025 — SheetCompressor (anclas
   estructurales, índice inverso, agregación por formato); compresión media 25×; +25,6 % en detección de
   tablas (GPT-4 en contexto) y 78,9 % F1 ajustado (resumen del resumen; leí el abstract vía búsqueda).
10. openpyxl-image-loader (PyPI, MIT, v1.0.5, 2020-01-23): https://pypi.org/project/openpyxl-image-loader/ —
    imágenes por celda a través de openpyxl; **sin mantenimiento desde 2020 y sin confirmar** soporte de
    imágenes en celda (probablemente solo flotantes). No lo recomiendo: el prototipo lee el XML directo.
11. python-calamine: https://pypi.org/project/python-calamine/ y
    https://simonwillison.net/2024/Jan/3/fastest-way-to-read-excel-in-python/ — lector Rust, motor de pandas
    ≥2.2; 4,6× más rápido que openpyxl en 1 M de filas (medición de terceros). No lee imágenes.
12. OWASP CSV Injection: https://owasp.org/www-community/attacks/CSV_Injection — celdas que empiezan con
    `= + - @` se interpretan como fórmula al reexportar; sanitizar al **exportar**, y tratar como dato al
    importar.

**Reutilizables sin costo de licencia**: openpyxl (MIT), python-calamine (MIT, ver repo), MarkItDown (MIT),
Docling (MIT), Pillow (HPND), pdfplumber (MIT, no consultado) y el propio módulo `zipfile`/`xml.etree`.
Claude (visión/PDF) es de pago por tokens; hay cuota de archivos gratis, no de inferencia.

### Límites por proveedor (comparativa)

| Proveedor | Imagen | Imágenes por petición | PDF | Estado |
|---|---|---|---|---|
| Anthropic API | 10 MB base64, 8000 px; >20 imágenes → 2000 px | 100 / 600 | 32 MB, 600 págs (100) | Verificado (oficial) |
| Anthropic vía Bedrock/Google | **5 MB** base64 | — | — | Verificado (oficial) |
| OpenAI | «20 MB por imagen, 500 imágenes, 50 MB por petición» vs «512 MB, 1.500 imágenes, 30.000 parches»: dos cifras contradictorias en la búsqueda | — | — | **NO VERIFICADO** (`platform.openai.com` y `developers.openai.com` bloqueados por el proxy) |
| Meta (Muse Spark) | tamaño máximo no publicado que yo pueda ver | 50 (incidencia de un tercero) | dice aceptar PDF | **NO VERIFICADO** (`dev.meta.ai` bloqueado; datos de terceros: Vercel community, opencode issue #48647) |

Implicación de diseño: normalizar **siempre** antes del proveedor: JPEG/WebP, lado largo ≤1.568 px (≤2.000
px si hay más de 20), ≤4 MB, máx. 20 por mensaje, y paginar. Así funciona en los tres y en Bedrock.

## 7. Coordinación

* **brian-modelos**: necesito de ustedes (a) qué modelo barato hace bien visión de fichas en español, (b)
  límites reales de OpenAI y Meta (yo no pude abrir sus docs), (c) precio por imagen para estimar el lote.
  Mi diseño es agnóstico: normaliza imágenes por el mínimo común.
* **brian-evals**: conjunto de pruebas de extracción propuesto (todo ya disponible): (1) el Excel real
  (`salida/*.candidatos.json` es la «verdad de oro» de las 6 discrepancias, 11 sin foto, 2 no crecientes);
  (2) `pruebas/test_extractor.py` (sintético: combinadas, fórmula sin caché, flotante, en celda,
  oculta, inyección); (3) faltan casos: encabezado desplazado, dos tablas en una hoja, precio «Desde $99»,
  fecha serial vs texto, CSV cp1252 con `;`, xlsx con macros, xlsx protegido con contraseña, foto de ficha
  inclinada.
* **seguridad (S-10, B-07, B-13)**: el contenido de celdas y de PDF es el vector de inyección indirecta más
  probable de Brian (subida por empleados o reenvío de proveedores). Medidas en el diseño: marcado con
  delimitador con nonce (hoy fijo: A-04), `sospecha_instruccion` por celda, aplicar solo con confirmación,
  regla de contaminación del turno, zip bomb/XML bomb, sin macros ni vínculos externos, retención del
  adjunto original (B-13: 30 d propuesto) y aviso de privacidad cuando el archivo trae datos personales
  (clientes/RUC) que van a un tercero (proveedor de IA).

## 8. Plan de arreglo (orden)

1. **P0 (S, sin IA)**: soportar `.xlsx`/`.xls`/`.docx` en `_leer_adjunto` con el extractor (vía `leer_archivo`);
   dejar de decodificar `.xls` como UTF-8; redimensionar imágenes en lugar de rechazar (`MAX_IMAGEN`).
2. **P0**: delimitador con nonce en `<<DATOS>>` (A-04) y `sospecha_instruccion`.
3. **P1 (M)**: `brian.importacion` + `.linea` (idempotencia, trazabilidad, valores previos) y
   `proponer/aplicar/deshacer_importacion_catalogo` con `modo_itbms` obligatorio y vista previa.
4. **P1**: cruce de fotos (zip o carpeta) y verificación visual opcional de fichas (modelo barato).
5. **P2**: PDF escaneado y Word con imágenes (conversión a PDF + visión), importación de clientes.
6. Mover `scripts/importar_catalogo.py` a usar el mismo extractor (una sola lectura de Excel en el repo).

## 9. NO VERIFICADO

* Límites de imagen/PDF de OpenAI y Meta (hosts bloqueados por el proxy; cifras de OpenAI contradictorias).
* Que la cadena richData del prototipo cubra todas las versiones de Excel (formato no documentado en
  ECMA-376; probado solo con un archivo sintético hecho a mano según la incidencia #302). No hay un
  `.xlsx` real con imágenes en celda en el repo.
* Que LibreOffice/Google Sheets guarden las imágenes en celda igual que Excel.
* Comportamiento de openpyxl ≥3.1 (el entorno tiene 3.0.9; el prototipo soporta ambas formas de
  `defined_names`, pero solo se ejecutó con 3.0.9).
* Precio por imagen y costo total de releer las 323 páginas (depende de `brian-modelos`).
* Si `mimetype` de un `.xlsx` llega vacío desde el navegador/Telegram (no probado; Telegram suele enviar
  `mime_type`, el panel usa `archivo.type` que puede ser `""`: `brian_panel.js:476,488`).
* Tiempos de procesamiento de archivos >5.000 filas (el Excel real tiene 219 filas: extracción 0,3 s).
* Si el dueño quiere tratar `Stock = «Sin confirmar»` como 0 o como desconocido en Odoo (decisión de negocio).

## 10. Prototipo

`docs/auditoria/ronda2/brian-excel-prototipo/`:

* `extractor.py` — extractor (~330 líneas, solo stdlib + openpyxl + Pillow). No usa IA ni Odoo.
* `pruebas/test_extractor.py` — 8 pruebas (`python3 -m unittest pruebas.test_extractor`; todas pasan).
* `salida/DCASA_listado_productos.intermedio.json` (185 KB) · `.resumen.json` · `.candidatos.json` (64 KB).
  Extracto del resumen medido: 4 hojas, 0 combinadas, 0 fórmulas, 0 imágenes, 0 riesgos; candidatos: 219 filas,
  199 códigos, alertas `duplicado_identico` 14, `duplicado_con_otro_precio` 6, `sin_foto_en_carpeta` 11,
  `codigo_con_minusculas` 12, `precios_por_tamano_no_crecientes` 2, `tamano_sin_precio` 1, `sin_precio` 1.
* Lo que el prototipo **no** hace: llamar a un modelo, escribir en Odoo, leer xls/docx/pdf, el mapeo con
  modelo de columnas ambiguas, ni paginación de hojas grandes (diseñado, no construido). `ruff` del repo
  solo revisa `addons`; el prototipo tiene 9 avisos de estilo (p. ej. `zip()` sin `strict=`), sin efecto.
