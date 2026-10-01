# r3-brian-documentos (ronda 3): motor de lectura de documentos de Brian

Fecha: 2026-10-01. Agente: `r3-brian-documentos`. Solo escribe en `docs/auditoria/ronda3/`.
Prototipo: `docs/auditoria/ronda3/brian-documentos/` (TypeScript compatible con Workers, probado en Node 22.22).

Mandato del dueño: «Brian debería poder leer fotos, documentos y estar muy bien entrenado en la
lectura de Excel, porque este negocio vive de Excel, de imágenes que vienen dentro de Excel, de
interpretar tablas, campos, celdas, variables, constantes. Este debe ser nuestro fuerte».

## 1. Resumen ejecutivo

1. **Hoy Brian no lee Excel ni Word** (sin cambios desde la ronda 2; `conversacion.py:480-498`).
   Con librerías estándar tampoco se cumpliría el mandato: **exceljs 4.4.0 se cae** con cualquier
   xlsx con imagen hecho por openpyxl (el Excel real del negocio es «generado por script») y, con
   un libro real de Excel 365, devuelve `#VALUE!` en las celdas con imagen; **SheetJS CE** no ve
   imágenes (función de pago) y su versión en npm (0.18.5) arrastra 2 avisos ALTOS sin arreglo
   publicado en npm; openpyxl ve las flotantes pero **no** las imágenes «en celda».
2. **Construí un lector propio** (~1 950 líneas TS, una sola dependencia: `fflate`; 42 KB
   minificado, 18 KB gzip) que corre en un Worker: zip por **rangos** (sirve directo sobre R2 sin
   cargar el archivo), XML en **streaming** con defensas (sin DTD/entidades, límites, zip bombs,
   entradas solapadas, cifrado), y produce el esquema intermedio **`dcasa.xlsx/2`** (compatible
   con `/1` de la ronda 2) con valor + fórmula, combinadas, hojas/filas/columnas ocultas, formatos,
   comentarios, enlaces, **imágenes flotantes con su celda ancla** e **imágenes en celda (richData)**
   resueltas, cuadros de texto, detección de **varias tablas y encabezados en varias filas**,
   roles de columna, **precios en texto normalizados** sin inventar, y señales de inyección.
   **49 pruebas en verde** (incluye el Excel real y 2 libros REALES de Excel 365 con imágenes en celda).
3. **Hallazgo de corrección**: el lector de imágenes en celda de la ronda 2 asigna la imagen
   **equivocada** cuando la celda tiene varios `<rc>` (caso real de Excel 365 con matrices
   dinámicas). Corregido y probado aquí (bitácora).
4. **Mediciones** (mediana de 3, máquina compartida): el Excel real se lee en ~0,1 s; 10 MB de
   solo celdas (1,24 M celdas) en ~4-5 s de CPU con **pico de heap 30-38 MB** (cabe en los 128 MB
   del isolate con margen); 50 MB sin sharedStrings cabe (42 MB, ~19 s de CPU); 48,6 MB con
   sharedStrings de 67 MB **no cabe** (OOM con el heap topado a ~120 MB). exceljs y SheetJS necesitan
   450-700 MB de RSS ya con 10 MB y 2,4-3,4 GB con 50 MB: **no caben**.
   Umbral propuesto (medido): **Worker** si `sharedStrings` ≤ 24 MB y el XML ≤ 160 MB descomprimidos
   (un xlsx de 49 MB con 40 fotos se lee en 0,3 s; uno de 48,6 MB con sharedStrings de 67 MB da OOM);
   por encima, **el mismo código TS en el Container** (Node), y LibreOffice solo para `.xls/.xlsb/.ods`.
5. **El modelo solo interviene donde hace falta**: columnas sin rol, texto libre, fotos y páginas
   escaneadas. Ve una **vista compacta** (el Excel real: ~1 400 caracteres ≈ 420 tokens, frente a
   ~20 700 si se mandara la hoja entera), envuelta como dato con **delimitador con nonce**, y todo lo
   que devuelve se **valida contra la celda que cita** (anti-alucinación). Importar = vista previa →
   confirmación humana → lotes idempotentes (llave `sha256:hoja:fila`) → reversión (probado).
6. **`toMarkdown()` de Workers AI no sirve como lector principal** (por documentación): acepta
   xlsx/xls/xlsb/ods/docx/csv, pero devuelve Markdown sin celdas, fórmulas ni anclas, y las imágenes
   las **describe** un modelo genérico (no extrae datos). Útil solo como vista rápida de formatos raros.
7. **Corrección a la ronda 2**: las 323 PNG de `up media/` **no** traen precio impreso (0 de 17
   revisadas); ~la mitad trae **medidas**. La visión sirve para medidas y tipo de mueble.
8. Costo típico por documento con Claude Sonnet 5.5 ($2/$10 por MTok): Excel del negocio ≈ **$0,004**;
   lista de proveedor con 40 fotos verificadas ≈ **$0,08**; foto suelta ≈ **$0,006**; con Meta Muse
   Spark 1.3 (precio NO VERIFICADO) ≈ 40-50 % menos.
9. Faltan (P0): integrar el lector como herramienta `leer_archivo` (en Odoo vía Container o en el
   Worker de r3-brian-agente), normalizar fotos antes del modelo, `proponer/aplicar/deshacer_importacion`
   y correr las **33 casos dorados nuevos** (`casos/dorado_documentos.jsonl`) junto a los 26 de la ronda 2.

## 2. Punto de partida (qué hace Brian hoy con adjuntos)

Sin cambios desde la ronda 2 (verificado hoy):

| Tema | Hoy | Evidencia |
|---|---|---|
| Lectura | Solo PDF con texto nativo (`PdfFileReader.extract_text`) y texto plano | `addons/dcasa_brian/models/conversacion.py:480-498` |
| `.xlsx` / `.docx` | «No puedo leer este tipo de archivo» | `conversacion.py:491` |
| `.xls` | Entra por `MIMES_TEXTO` y se decodifica como UTF-8 (basura) | `conversacion.py:89,487-489` |
| CSV de Excel en español (cp1252, «;») | Se decodifica como UTF-8 con `errors='replace'`: se pierden tildes y «ñ» | `conversacion.py:487-489` |
| Imágenes | > 5 MB se rechazan sin redimensionar (54 de las 323 PNG del negocio); solo la última imagen va al modelo | `conversacion.py:83,594-602` |
| Texto extraído | Recorte mudo a 20 000 caracteres | `conversacion.py:82,496-497` |
| Delimitador de datos | `<<DATOS …>>` / `<<FIN DE LOS DATOS>>` fijo (falsificable) | `conversacion.py:473-477` |
| Telegram | 10 MB por archivo; foto (la mayor) o documento | `models/telegram.py:45,188-204,383-402` |

## 3. Formatos y casos a cubrir

| Formato | Casos que el motor debe resolver | Estado en el prototipo |
|---|---|---|
| `.xlsx` / `.xlsm` | valores y fórmulas (con y sin caché, compartidas), combinadas, encabezados en varias filas, varias tablas por hoja, hojas/filas/columnas ocultas, formatos de número/moneda/fecha (incl. sistema 1904), comentarios (clásicos y en hilo), hipervínculos, nombres definidos, imágenes **flotantes** (oneCell/twoCell/absolute) con celda ancla y texto alternativo, imágenes **en celda** (richData: «Colocar en celda» / `IMAGE()`; también imágenes web), cuadros de texto, precios en texto, macros/vínculos externos/OLE (aviso, nunca se ejecutan) | **Hecho** (`src/xlsx.ts`, `src/tablas.ts`, `src/precios.ts`) |
| `.csv` / `.tsv` | UTF-8 con/sin BOM, UTF-16, **Windows-1252 con «;» y coma decimal** | **Hecho** (`src/csv.ts`) |
| `.xls` (97-2003), `.xlsb`, `.ods` | convertir a xlsx en Container (LibreOffice / calamine) | Detección por firma y ruteo (`src/firma.ts`, `src/documento.ts`) |
| xlsx/docx **con contraseña** | es un contenedor OLE con `EncryptedPackage`, no un zip | Detectado; se pide guardarlo sin contraseña |
| `.docx` | párrafos, tablas, imágenes en línea con texto alternativo | **Hecho** (`src/docx.ts`) |
| PDF | texto nativo por página; escaneado/foto → visión | **Hecho** el texto (unpdf); páginas sin texto → `necesita_vision` (`src/pdf.ts`) |
| Fotos (fichas, listas de proveedores, facturas, notas a mano) | visión con salida estructurada validada; normalizar a JPEG/WebP ≤ 1568 px | Diseño (§6), costo (§8) y casos dorados reales (§9) |

## 4. Evaluación de opciones y mediciones

### 4.1 Límites oficiales que mandan (MCP de Cloudflare, consultado 2026-10-01)

| Límite | Valor | Fuente |
|---|---|---|
| Memoria por isolate | **128 MB**, «including the JavaScript heap and WebAssembly allocations»; por isolate, compartida entre peticiones concurrentes | https://developers.cloudflare.com/workers/platform/limits/ (el fragmento no trae «Last updated») |
| CPU por petición HTTP (Paid) | 5 min (30 s por defecto, `limits.cpu_ms`) | ídem y /workers/wrangler/configuration/ |
| Cuerpo de petición | 100 MB (planes Free/Pro de la zona) | ídem |
| Buenas prácticas | no bufferizar cuerpos grandes: *stream* (skill oficial `workers-best-practices`, `references/runtime-patterns.md`) | skill clonada |
| Images binding | entrada ≤ 20 MB; $0,50 por 1 000 transformaciones únicas tras 5 000 gratis/mes | https://developers.cloudflare.com/images/optimization/binding/ (Last updated 2026-09-02), /images/pricing/ |
| Workers AI | $0,011 por 1 000 Neuronas; 10 000/día gratis | https://developers.cloudflare.com/workers-ai/platform/pricing/ (Last updated 2026-09-17) |

### 4.2 Librerías JS para el Worker (medido)

| Opción | Imágenes flotantes | Imágenes en celda | Streaming / rangos | Seguridad | Veredicto |
|---|---|---|---|---|---|
| **exceljs 4.4.0** | Sí en libros de Excel; **se cae** con libros de openpyxl (`xlsx.js:100`, `drawing.anchors` undefined) | No (`{"error":"#VALUE!"}`) | Lector streaming solo con streams de Node | Carga todo; 700 MB RSS con 10 MB | **Descartado** |
| **SheetJS CE** (npm 0.18.5) | No (edición Pro) | No (`#VALUE!`) | No | 2 avisos ALTOS sin arreglo en npm (GHSA-4r6h-8v6p-xvw6, GHSA-5pgg-2g8v-p4x9); las versiones corregidas solo en cdn.sheetjs.com (403 aquí) | **Descartado** |
| **fflate + lector propio** (este prototipo) | Sí (oneCell/twoCell/absolute, alt) | **Sí** (cadena completa, multi-`rc`, clave por nombre, web) | Sí: zip por rangos + XML por trozos | Sin DTD, límites, bombas, cifrado | **Elegido** |
| unpdf 1.8.1 (pdf.js) | — | — | — | Texto por página | **Elegido** para PDF (1,6 MB min; 0,5 MB gzip) |
| mammoth 1.13 | Convierte a HTML | — | — | — | No necesario: el lector propio de docx (71 líneas) da párrafos, tablas e imágenes con alt |

### 4.3 Workers AI `toMarkdown()` y visión/PDF nativos de los modelos (por documentación)

* **`toMarkdown()`**: formatos `.xlsx .xlsm .xlsb .xls .et .docx .ods .odt .csv .numbers`, PDF e
  imágenes (https://developers.cloudflare.com/ai-search/configuration/data-source/). Las imágenes se
  reducen a 1280×720, pasan por `detr-resnet-50` y `gemma-4-26b-a4b-it` para **describirlas**
  (https://developers.cloudflare.com/workers-ai/features/markdown-conversion/how-it-works/). Para Excel
  la documentación no dice que conserve fórmulas, combinadas, imágenes ni anclas (y no hay referencias
  de celda en Markdown): **pierde justo lo que pide el dueño**. Costo: las imágenes gastan Neuronas; si
  la conversión de documentos es gratis no lo pude confirmar (el MCP no devolvió la sección «Pricing»
  de la página; NO VERIFICADO, preguntado a r3-cf-plataforma). Uso recomendado: vista rápida de
  `.xls/.xlsb/.ods/.numbers` antes de convertirlos en el Container.
* **Claude** (https://platform.claude.com/docs/en/build-with-claude/vision y /pdf-support, leídas hoy):
  imágenes JPEG/PNG/GIF/WebP, 10 MB por imagen (base64, API directa; 5 MB en Bedrock/Google), 8000×8000
  px, **más de 20 imágenes → máx. 2000 px por lado**, 600 imágenes por petición (100 con contexto de
  200k), petición ≤ 32 MB; costo `⌈ancho/28⌉×⌈alto/28⌉`; nivel estándar 1568 px/1568 tokens, **alta
  resolución (Claude 4.7 y posteriores) 2576 px/4784 tokens**. PDF: 32 MB, 600 páginas (100 si el
  contexto < 1M), cada página = texto (1 500-3 000 tokens) + imagen; **`.xlsx/.docx` no son bloques
  `document`**: hay que convertirlos (lo hace este lector).
* **Meta Muse Spark 1.3** (de `ronda3/brian-agente.md` §2.3, r3-brian-agente): 50 imágenes por
  solicitud, 50 MB por imagen, PDF solo por Responses `input_file` (texto de 100 páginas, imágenes de 50),
  **sin soporte nativo de xlsx**; precio 1,25/0,15/4,25 por MTok **NO VERIFICADO**; conteo de tokens de
  imagen no publicado (NO VERIFICADO).
* Diseño agnóstico: normalizar **siempre** antes del proveedor (JPEG/WebP, lado largo ≤ 1568 px, ≤ 4 MB,
  ≤ 20 imágenes por mensaje); así funciona en Claude (los dos niveles), Bedrock y Meta.

### 4.4 Mediciones de tiempo y memoria (mediana de 3 corridas)

Node v22.22.0, Python 3.11, 4 vCPU compartidas con otros 7 agentes; 3 corridas por combinación en procesos aparte y **mediana** (exceljs/SheetJS/openpyxl completo con > 40 MB: 1 corrida). `heap pico` = máximo de `heapUsed + arrayBuffers` muestreado en cada lectura de la fuente (solo el prototipo por rangos); `RSS Δ` = aumento del máximo de memoria residente del proceso (incluye código, memoria libre no devuelta y basura no recolectada: cota superior). Datos crudos: `brian-documentos/medicion/salida/mediciones.json` (generado 2026-10-01T01:08Z). Comando: `npm run medir` (o `node --experimental-strip-types medicion/medir.ts 3`).

| Archivo | Lector | Tiempo (ms) | CPU (ms) | Heap pico (MB) | RSS Δ (MB) | Resultado |
|---|---|---:|---:|---:|---:|---|
| Excel real (40 KB, 4 hojas, 2 637 celdas) | prototipo (R2 por rangos) | 87 | 169 | 2.3 | 7.2 | Productos:220f/1000c/0img,Imágenes (proyecto):332f/1328c/0im |
| Excel real (40 KB, 4 hojas, 2 637 celdas) | prototipo, heap topado ~120 MB | 68 | 156 | 2.2 | 7.2 | Productos:220f/1000c/0img,Imágenes (proyecto):332f/1328c/0im |
| Excel real (40 KB, 4 hojas, 2 637 celdas) | prototipo (archivo en memoria) | 106 | 161 | — | 8 | Productos:220f/1000c/0img,Imágenes (proyecto):332f/1328c/0im |
| Excel real (40 KB, 4 hojas, 2 637 celdas) | exceljs 4.4.0 | 168 | 296 | 10.5 | 14 | Productos:220f/0img,Imágenes (proyecto):332f/0img,Todas las  |
| Excel real (40 KB, 4 hojas, 2 637 celdas) | SheetJS CE 0.18.5 | 113 | 147 | 2.2 | 7.5 | Productos:A1:G220,Imágenes (proyecto):A1:D332,Todas las fich |
| Excel real (40 KB, 4 hojas, 2 637 celdas) | openpyxl 3.0.9 read_only | 39 | 39 | — | 1.4 | 814 filas, 0 img |
| Excel real (40 KB, 4 hojas, 2 637 celdas) | openpyxl 3.0.9 completo | 53 | 53 | — | 2.4 | 814 filas, 0 img |
| sintético (12 KB, 4 imágenes) | prototipo (R2 por rangos) | 54 | 83 | 1.7 | 11.4 | Lista Proveedor:15f/55c/4img,Costos (oculta):2f/4c/0img |
| sintético (12 KB, 4 imágenes) | prototipo, heap topado ~120 MB | 49 | 45 | 1.8 | 4.2 | Lista Proveedor:15f/55c/4img,Costos (oculta):2f/4c/0img |
| sintético (12 KB, 4 imágenes) | prototipo (archivo en memoria) | 46 | 48 | — | 4.7 | Lista Proveedor:15f/55c/4img,Costos (oculta):2f/4c/0img |
| sintético (12 KB, 4 imágenes) | exceljs 4.4.0 | — | — | — | — | **falla**: Cannot read properties of undefined (reading 'anchors') |
| sintético (12 KB, 4 imágenes) | SheetJS CE 0.18.5 | 37 | 43 | 1.5 | 0 | Lista Proveedor:A1:H18,Costos (oculta):A1:B2 |
| sintético (12 KB, 4 imágenes) | openpyxl 3.0.9 read_only | 8 | 8 | — | 0.4 | 20 filas, 0 img |
| sintético (12 KB, 4 imágenes) | openpyxl 3.0.9 completo | 21 | 21 | — | 1.7 | 20 filas, 2 img |
| 1 MB (124 mil celdas) | prototipo (R2 por rangos) | 866 | 810 | 11.9 | 48.1 | Datos:16913f/124030c/0img |
| 1 MB (124 mil celdas) | prototipo, heap topado ~120 MB | 888 | 956 | 11 | 43.2 | Datos:16913f/124030c/0img |
| 1 MB (124 mil celdas) | prototipo (archivo en memoria) | 693 | 832 | — | 49 | Datos:16913f/124030c/0img |
| 1 MB (124 mil celdas) | exceljs 4.4.0 | 1385 | 1491 | 58.6 | 103.7 | Datos:16913f/0img |
| 1 MB (124 mil celdas) | SheetJS CE 0.18.5 | 1146 | 1157 | 42.4 | 71.2 | Datos:A1:H16913 |
| 1 MB (124 mil celdas) | openpyxl 3.0.9 read_only | 1708 | 1698 | — | 2.4 | 16913 filas, 0 img |
| 1 MB (124 mil celdas) | openpyxl 3.0.9 completo | 2373 | 2286 | — | 55.6 | 16913 filas, 0 img |
| 10 MB (1,24 M celdas, inlineStr) | prototipo (R2 por rangos) | 4138 | 4359 | 39.3 | 103.1 | Datos:169126f/1240258c/0img |
| 10 MB (1,24 M celdas, inlineStr) | prototipo, heap topado ~120 MB | 4500 | 4548 | 30.3 | 83.8 | Datos:169126f/1240258c/0img |
| 10 MB (1,24 M celdas, inlineStr) | prototipo (archivo en memoria) | 3979 | 4391 | — | 108.7 | Datos:169126f/1240258c/0img |
| 10 MB (1,24 M celdas, inlineStr) | exceljs 4.4.0 | 7609 | 10330 | 615.8 | 696.2 | Datos:169126f/0img |
| 10 MB (1,24 M celdas, inlineStr) | SheetJS CE 0.18.5 | 10703 | 12773 | 294.9 | 448.4 | Datos:A1:H169126 |
| 10 MB (1,24 M celdas, inlineStr) | openpyxl 3.0.9 read_only | 18222 | 18031 | — | 16.1 | 169126 filas, 0 img |
| 10 MB (1,24 M celdas, inlineStr) | openpyxl 3.0.9 completo | 25455 | 25214 | — | 549.4 | 169126 filas, 0 img |
| 10 MB (1,24 M celdas, sharedStrings 14 MB) | prototipo (R2 por rangos) | 4280 | 5406 | 71.7 | 170.9 | Datos:169126f/1240258c/0img |
| 10 MB (1,24 M celdas, sharedStrings 14 MB) | prototipo, heap topado ~120 MB | 4410 | 6410 | 38.2 | 116.8 | Datos:169126f/1240258c/0img |
| 10 MB (1,24 M celdas, sharedStrings 14 MB) | prototipo (archivo en memoria) | 4191 | 5257 | — | 182.9 | Datos:169126f/1240258c/0img |
| 10 MB (1,24 M celdas, sharedStrings 14 MB) | exceljs 4.4.0 | 7842 | 10555 | 624.9 | 706.4 | Datos:169126f/0img |
| 10 MB (1,24 M celdas, sharedStrings 14 MB) | SheetJS CE 0.18.5 | 9585 | 10776 | 401.3 | 500.1 | Datos:A1:H169126 |
| 10 MB (1,24 M celdas, sharedStrings 14 MB) | openpyxl 3.0.9 read_only | 15755 | 15608 | — | 69.4 | 169126 filas, 0 img |
| 10 MB (1,24 M celdas, sharedStrings 14 MB) | openpyxl 3.0.9 completo | 22405 | 22160 | — | 530.1 | 169126 filas, 0 img |
| 50 MB (6,2 M celdas, inlineStr, XML 340 MB) | prototipo (R2 por rangos) | 18133 | 18952 | 43.5 | 126.4 | Datos:845626f/6201258c/0img |
| 50 MB (6,2 M celdas, inlineStr, XML 340 MB) | prototipo, heap topado ~120 MB | 18898 | 20104 | 42.3 | 98.2 | Datos:845626f/6201258c/0img |
| 50 MB (6,2 M celdas, inlineStr, XML 340 MB) | prototipo (archivo en memoria) | 18661 | 19054 | — | 174.9 | Datos:845626f/6201258c/0img |
| 50 MB (6,2 M celdas, inlineStr, XML 340 MB) | exceljs 4.4.0 | 61420 | 65964 | 3122 | 3404.3 | Datos:845626f/0img |
| 50 MB (6,2 M celdas, inlineStr, XML 340 MB) | SheetJS CE 0.18.5 | 86600 | 93040 | 1583.6 | 2481.3 | Datos:A1:H845626 |
| 50 MB (6,2 M celdas, inlineStr, XML 340 MB) | openpyxl 3.0.9 read_only | 95204 | 93560 | — | 73 | 845626 filas, 0 img |
| 50 MB (6,2 M celdas, inlineStr, XML 340 MB) | openpyxl 3.0.9 completo | 127228 | 125423 | — | 2822.7 | 845626 filas, 0 img |
| 48,6 MB (6,2 M celdas, sharedStrings 67 MB) | prototipo (R2 por rangos) | 21338 | 26165 | 146.7 | 390.9 | Datos:845626f/6201258c/0img |
| 48,6 MB (6,2 M celdas, sharedStrings 67 MB) | prototipo, heap topado ~120 MB | — | — | — | — | **OOM** con el tope (no cabe) |
| 48,6 MB (6,2 M celdas, sharedStrings 67 MB) | prototipo (archivo en memoria) | 20463 | 28795 | — | 429.4 | Datos:845626f/6201258c/0img |
| 48,6 MB (6,2 M celdas, sharedStrings 67 MB) | exceljs 4.4.0 | 45824 | 58261 | 2382.8 | 2663.4 | Datos:845626f/0img |
| 48,6 MB (6,2 M celdas, sharedStrings 67 MB) | SheetJS CE 0.18.5 | 82695 | 110192 | 1730.6 | 2379.9 | Datos:A1:H845626 |
| 48,6 MB (6,2 M celdas, sharedStrings 67 MB) | openpyxl 3.0.9 read_only | 84689 | 83509 | — | 324.8 | 845626 filas, 0 img |
| 48,6 MB (6,2 M celdas, sharedStrings 67 MB) | openpyxl 3.0.9 completo | 118659 | 117356 | — | 2718.4 | 845626 filas, 0 img |
| 49 MB (300 filas + 40 imágenes de 1,2 MB) | prototipo (R2 por rangos) | 300 | 441 | 36.3 | 44.4 | Datos:301f/2208c/40img |
| 49 MB (300 filas + 40 imágenes de 1,2 MB) | prototipo, heap topado ~120 MB | 309 | 503 | 35.2 | 43.2 | Datos:301f/2208c/40img |
| 49 MB (300 filas + 40 imágenes de 1,2 MB) | prototipo (archivo en memoria) | 407 | 561 | — | 94.1 | Datos:301f/2208c/40img |
| 49 MB (300 filas + 40 imágenes de 1,2 MB) | exceljs 4.4.0 | — | — | — | — | **falla**: Cannot read properties of undefined (reading 'anchors') |
| 49 MB (300 filas + 40 imágenes de 1,2 MB) | SheetJS CE 0.18.5 | 321 | 347 | 53.3 | 47.4 | Datos:A1:H301 |
| 49 MB (300 filas + 40 imágenes de 1,2 MB) | openpyxl 3.0.9 read_only | 28 | 28 | — | 1.2 | 301 filas, 0 img |
| 49 MB (300 filas + 40 imágenes de 1,2 MB) | openpyxl 3.0.9 completo | 128 | 128 | — | 53.2 | 301 filas, 40 img |

Lectura de la tabla:

* **Cabe en el isolate (128 MB)**: con el heap de V8 topado a ~120 MB el prototipo lee el Excel real,
  1 MB, 10 MB (inlineStr y con sharedStrings de 14 MB: pico 30-38 MB), 50 MB sin sharedStrings (pico
  ~42 MB: el XML de 340 MB pasa en streaming) y 49 MB con 40 fotos (0,3 s). **No cabe** 48,6 MB con
  sharedStrings de 67 MB (OOM con el tope; sin tope llega a ~147 MB de heap). Una corrida previa, antes
  de optimizar el tokenizador, pasó con 87 MB: está en el borde, no es apto. ⇒ lo que manda es el
  tamaño **descomprimido** de `sharedStrings.xml`, no el del archivo.
* **CPU**: ~4-5 s para 1,24 M celdas; ~19-26 s para 6,2 M celdas (bajo los 30 s por defecto, con poco
  margen; configurable hasta 5 min). El perfil (`--cpu-prof`, 10 MB) muestra 34 % tokenizador, 16 %
  inflate (fflate), 14 % atributos: hay margen de optimización (§9, P2).
* **exceljs / SheetJS**: 450-700 MB de RSS ya con 10 MB y 2,4-3,4 GB con 50 MB: no caben en un Worker;
  exceljs además se cae con los libros de openpyxl. **openpyxl read_only** es frugal en memoria
  (16-73 MB con inlineStr; 325 MB con sharedStrings de 67 MB) pero 4-5× más lento que el prototipo y no
  ve imágenes en celda (`openpyxl-full` en el sintético reporta 2 imágenes de 4).
* **Lecturas de R2** (`medicion/r2_peticiones.ts`, bloques de 256 KB): Excel real y sintético = 1
  petición; 10 MB = 41 peticiones (operaciones clase B: costo despreciable).
* **Umbral para el Container**: `sharedStrings.xml` > 24 MB **o** XML de hojas + sharedStrings > 160 MB
  descomprimidos (≈ 10 s de CPU) — se decide leyendo solo el directorio central del zip (1 petición),
  antes de descomprimir nada (`src/documento.ts`, probado con los fixtures grandes).

### 4.5 Qué va dónde (decisión)

| Entrada | Dónde | Por qué |
|---|---|---|
| xlsx/xlsm con sharedStrings ≤ 24 MB y XML ≤ 160 MB descomprimidos (sin importar cuántas fotos traiga) | **Worker** (lector TS) | Medido: pico de heap ≤ ~45 MB, CPU ≤ ~10 s |
| xlsx/xlsm mayor | **Container**, el MISMO lector TS en Node (sin tope de 128 MB) | Una sola base de código; openpyxl es 4× más lento y no ve imágenes en celda |
| `.xls`, `.xlsb`, `.ods`, `.numbers` | Container: LibreOffice → xlsx → lector | Formatos binarios/ODF; `toMarkdown` como vista previa rápida |
| CSV/TSV, docx | Worker | Ligeros |
| PDF con texto | Worker (unpdf) | Texto por página; tablas dudosas → modelo |
| PDF escaneado / páginas sin texto | **Modelo** (Claude: bloque `document`; Meta: Responses `input_file`) | Visión + texto por página |
| Fotos | **Modelo**, tras normalizar con el Images binding | Resize ≤ 1568 px, JPEG/WebP; HEIC/TIFF/BMP convertidos |
| Protegido con contraseña | Rechazar con mensaje | No se puede abrir sin la clave |

## 5. Prototipo

### 5.1 Estructura

```
docs/auditoria/ronda3/brian-documentos/
  src/fuente.ts       Fuente con acceso aleatorio: bytes, R2 por rangos (get con range) y caché de bloques
  src/zip.ts          ZIP defensivo por rangos (límites, razón, conteo real, solapadas, cifrado, ZIP64→Container)
  src/xml.ts          Tokenizador XML en streaming sin DTD/entidades externas
  src/firma.ts        Detección por firma: xlsx/xlsm/xlsb/ods/docx/pptx/pdf/OLE/OLE cifrado/imágenes/texto
  src/xlsx.ts         Lector → dcasa.xlsx/2 (ventana + resumen completo; richData; dibujos; comentarios)
  src/tablas.ts       Bloques, títulos, encabezados multifila, roles por palabras clave, registros con celdas
  src/precios.ts      Precios en texto («Full $149.99 · Queen $169.99», «B/. 1.329,99», «Desde $59.99», «$—»)
  src/inyeccion.ts    Señales de instrucciones incrustadas en datos
  src/csv.ts docx.ts pdf.ts   Otros formatos al mismo modelo mental de tabla/bloque
  src/modelo.ts       Vista compacta + nonce, JSON Schema de mapeo, validación anti-alucinación
  src/importacion.ts  Vista previa, lotes idempotentes, aplicar y revertir (sin Odoo)
  src/documento.ts    Ruteo Worker / Container / modelo / rechazo con umbrales medidos
  fixtures/           generar_fixtures.py (pequeños versionados; grandes con --grandes, en .gitignore)
  casos/              generar_casos.ts → dorado_documentos.jsonl (33 casos nuevos)
  medicion/           uno.ts, uno_openpyxl.py, medir.ts, tokens.ts, salida/mediciones.json
  test/lector.test.ts 49 pruebas (vitest)
```

Reproducir: `cd docs/auditoria/ronda3/brian-documentos && npm install && python3 fixtures/generar_fixtures.py --grandes && ./fixtures/descargar_externos.sh && npm test && npx tsc --noEmit && npm run medir`.

### 5.2 Imágenes en celda: estructura real de Excel 365 y su fuente

La cadena se tomó de libros **guardados por Excel** (`docProps/app.xml`: `Application=Microsoft
Excel`, `AppVersion 16.0300`) del proyecto `dalmartin/xlcellimage` (tests/data, commit `fa591235`,
2026-08-24, GPL-3: se descargan con `fixtures/descargar_externos.sh`, **no** se versionan), corroborada
por la especificación MS-XLSX («Local Image Type»: `_rvRel:LocalImageIdentifier` es índice 0-based a
`CT_RichValueRelRelationship`; `CalcOrigin` = cómo se creó el valor; resumen del buscador, la página de
learn.microsoft.com está bloqueada por el proxy) y la incidencia `yfedoseev/office_oxide#302`:

```
celda  <c r="F10" t="e" vm="2"><v>#VALUE!</v></c>          (vm 1-based; #VALUE! = reserva para lectores viejos)
xl/metadata.xml  metadataTypes: [XLDAPR, XLRICHVALUE]
                 valueMetadata/bk[vm-1] = <rc t="1" v="0"/><rc t="2" v="1"/>   ← elegir el rc cuyo t→XLRICHVALUE
                 futureMetadata[XLRICHVALUE]/bk[v]/…/xlrd:rvb i="1"            (v e i 0-based)
xl/richData/rdrichvalue.xml           rv[i] s="1": <v>5</v><v>1</v><v>Colchón Queen…</v>
xl/richData/rdrichvaluestructure.xml  s[1] t="_localImage": k=CalcOrigin, k=_rvRel:LocalImageIdentifier, k=Text
                                      ← el identificador se busca POR NOMBRE de clave, no por posición
xl/richData/richValueRel.xml          rel[identificador] r:id="rId2"
xl/richData/_rels/richValueRel.xml.rels  rId2 → ../media/encelda2.png
```

El fixture sintético (`sintetico.xlsx`) reproduce esa estructura a mano con dos trampas: F10 con dos
`<rc>` (XLDAPR primero) y una estructura con `CalcOrigin` antes del identificador. El prototipo de la
ronda 2 falla en ambas (bitácora); éste las resuelve, y además las 3 celdas de los libros reales.

### 5.3 Esquema intermedio `dcasa.xlsx/2` (por qué una v2)

Mantiene las claves de `/1` (`hojas[].estado/dimension/combinadas/filas_ocultas/imagenes/celdas{A1:{valor,formula,…}}`)
y agrega lo que hacía falta para que el modelo y la importación trabajen con trazabilidad:
`tipo` por celda (`n/s/b/e/d/f_sin_cache/imagen`), `clase_formato` (moneda/porcentaje/fecha), `combina`/`combinada_en`,
`imagen` (id) en la celda, `precios` normalizados con `literal`, `oculta`, `sospecha_instruccion`;
por hoja `resumen` completo (aunque la ventana sea parcial), `ventana` (paginación: `leer_archivo rango=…`),
`tablas` (rango, título, filas de encabezado, columnas con rol y confianza), `cuadros_texto`; por imagen
`id` (sha256), `tipo`, `celda`/`hasta`, `anclaje`, `alt`, `calc_origin`, dimensiones sin decodificar píxeles.

### 5.4 Pruebas (comando y salida)

```
$ cd docs/auditoria/ronda3/brian-documentos && npx tsc --noEmit && echo "tsc OK" && npx vitest run
tsc OK
 ✓ test/lector.test.ts (49 tests) 3757ms
 Test Files  1 passed (1)
      Tests  49 passed (49)
   Duration  4.70s (transform 358ms, setup 0ms, collect 561ms, tests 3.76s, environment 0ms, prepare 83ms)
```

(Con los fixtures grandes y los externos presentes; sin ellos, 2 bloques se saltan solos.)

Cubren: sintético (hojas ocultas, combinadas, fórmulas con/sin caché, moneda y fecha, fila oculta,
comentario, enlace, flotantes oneCell/twoCell, en celda con multi-`rc` y alt, precios en texto, inyección,
2 tablas + encabezado de 2 filas, registros con imágenes, ventana por rango, lectura desde R2 simulado
por rangos); Excel real (sha `731580f9…`, 219 filas, 199 códigos únicos, roles de columna, alertas
D142/D171/D182 = mismas 2 no crecientes + tamaño sin precio de la ronda 2); 2 libros reales de Excel 365;
ruteo con los fixtures grandes; defensas (zip bomb de 200 MB, encabezado que miente, entradas solapadas, DOCTYPE/«billion laughs»,
entidad desconocida, XML partido en cualquier punto, rutas `..`, cifrado, macros y vínculos externos);
firma y ruteo; precios; CSV cp1252; Word; PDF nativo vs escaneado; vista para el modelo con nonce,
validación anti-alucinación y de mapeo; plan de importación, aplicación idempotente por lotes y reversión.

## 6. Flujo completo para Brian

```
adjunto (panel / Telegram / MCP*) ─► R2 (clave = sha256, DigestStream al subir) ─► 0 firma ─► ruteo (§4.5)
   │                                                                                          │
   │  1 extracción determinista (Worker o Container, mismo lector) ─► dcasa.xlsx/2 (ventana+resumen)
   │  2 interpretación determinista: tablas, encabezados, roles, precios, alertas, imágenes↔fila
   │  3 modelo SOLO si: columna con rol null · texto libre que la regex no entiende · foto/página escaneada
   │       entrada = vista compacta con nonce (≈ 400-2 000 tokens) + imágenes normalizadas (≤ 1568 px)
   │       salida  = JSON Schema estricto (ESQUEMA_MAPEO / extracción con `celda`|`pagina` + `literal`)
   │       validar = valor ⊂ literal ⊂ fuente citada; si no, se descarta y se reporta
   │  4 vista previa (brian.importacion borrador): N crear / N actualizar (antes→después) / N omitir /
   │       alertas primero (duplicados, sin precio, «$—», no creciente, ocultas, inyección, costo)
   │  5 confirmación humana (tarjeta con valores reales; modo_itbms obligatorio; >30 % de cambio → 2ª)
   │  6 aplicar por lotes de 50 con savepoint; llave sha256:hoja:fila; reenviar = 0 escrituras
   └► 7 revertir: creados → archivar; actualizados → restaurar `antes` si write_date no cambió
* MCP: sin canal de archivos (1 MB JSON-RPC); aceptar solo `r2_key` subida por el panel/Telegram.
```

Transporte (acordado con r3-brian-agente, bitácora): el agente recibe una **clave de R2**, nunca bytes; el
lector usa `fuenteR2` (lecturas por rango); si el archivo supera el umbral del Worker, un paso de Workflow /
Container lo procesa y devuelve una referencia (la ventana `dcasa.xlsx/2` mide KB, muy por debajo del 1 MiB
por paso de Workflow).

Herramientas (contrato acordado con r3-brian-agente y r3-brian-habilidades, mismo catálogo en chat,
Telegram y MCP): `leer_archivo(adjunto, hoja?, rango?, max_filas?)` (lectura; devuelve resumen + ventana),
`ver_imagen(adjunto, celda|pagina|indice)` (lectura; miniatura normalizada), `extraer_de_imagen(adjunto,
esquema)` (lectura; modelo con visión y validación), `proponer_importacion_catalogo(adjunto, hoja, tabla,
modo_itbms, mapa_columnas?)` (escribe solo el borrador), `aplicar_importacion(importacion_id, lotes?)`
(**sensible**, nunca desde MCP; `modo_itbms` explícito, para D'CASA `mas_itbms`), `deshacer_importacion(importacion_id, motivo)` (**sensible**).

## 7. Política ante inyección (celdas, imágenes, PDF)

1. **Estructural, no por filtro**: leer un archivo nunca habilita una escritura. `aplicar_importacion`
   solo existe tras una vista previa y una confirmación humana con los valores reales; desde MCP nunca.
2. Todo contenido de archivo va como **dato** con delimitador de **nonce aleatorio** por petición
   (`<dato origen="archivo#Hoja!A4:H11" id="3t5f2i03285i">…</dato id="…">`); el contenido no puede cerrar
   el bloque (probado). Instrucciones del operador fuera de ese bloque.
3. **Señales** (`src/inyeccion.ts`): celdas, comentarios, texto alternativo de imágenes, cuadros de
   texto, párrafos de Word, texto de PDF y lo que el modelo transcribe de una foto se marcan
   `sospecha_instruccion`; la vista previa los muestra primero y exige confirmación reforzada.
4. **Turno contaminado**: si en el turno entró contenido no confiable, ninguna herramienta sensible se
   ejecuta sin una confirmación nueva (regla B-07c de la ronda 2).
5. **Fotos**: el texto que el modelo lee de una imagen es dato; nunca se ejecuta (caso `ADV-05`).
6. Sin macros, sin vínculos externos, sin OLE incrustado, sin DTD; zip/XML con límites (§5.4).
7. Privacidad (Ley 81/2019; el dueño aceptó Meta `-contributor`, que entrena con los prompts): archivos con datos personales (clientes, RUC, celulares) avisan antes de mandarse al
   proveedor de IA; el proveedor nunca recibe el binario, solo la vista.

## 8. Costo en tokens por documento típico

Precios oficiales Claude (skill `claude-api`, caché 2026-09-25): Sonnet 5.5 $2/$10 por MTok (lectura de
caché $0,20), Haiku 4.5 $1/$5, Opus 5.5 $4/$20. Meta Muse Spark 1.3: $1,25/$4,25 (NO VERIFICADO, r3-brian-agente).
Tokens de texto: caracteres/3,3 (estimación de la ronda 2, no el tokenizador real); visión: fórmula oficial
(`src/imagenes.ts`, `medicion/tokens.ts`). Sin contar el prompt de sistema ni las herramientas (eso lo mide
r3-brian-habilidades).

| Documento | Lo que ve el modelo | Tokens entrada | Salida | Sonnet 5.5 | Haiku 4.5 | Muse Spark 1.3* |
|---|---|---|---|---|---|---|
| Excel real del negocio (219 filas), «importa» | vista compacta 1 383 car. (el resto lo hace código) | ~420 | ~300 (preguntas/mapeo) | **$0,004** | $0,002 | $0,002 |
| Ídem si se mandara la hoja entera (como intentaría hoy un lector ingenuo) | JSON de celdas 68 227 car. | ~20 700 | ~300 | $0,044 | $0,022 | $0,027 |
| Lista de proveedor: 300 filas + 40 fotos en celda, verificar fotos | vista ~2 000 + 40 miniaturas a 1024 px (777 c/u en alta resolución) | ~33 000 | ~2 000 | **$0,086** | $0,043 | $0,050 |
| Foto suelta de ficha 1536×2761 (medidas) | reducida a 1568 px en alta res. | 1 792 + 200 | ~150 | **$0,0055** | $0,0025 (1 568 tokens) | $0,0031 |
| Ídem SIN reducir (alta resolución) | 4 784 | 4 984 | ~150 | $0,0115 | n/a | $0,0069 |
| Foto de celular 4032×3024 (factura) reducida a 1568 px | 2 352 + 200 | ~400 | $0,0091 | $0,0038 (1 568) | $0,0049 |
| Factura PDF 1 página escaneada (Claude: texto + imagen de la página) | ~1 500-3 000 + ~2 700 | ~4 200-5 700 | ~400 | $0,012-0,015 | $0,005-0,007 | NO VERIFICADO |
| PDF de 10 páginas con texto, extraído en el Worker | ~500/página como texto | ~5 000 | ~500 | $0,015 | $0,0075 | $0,0084 |

\* Meta: mismo conteo de tokens supuesto (NO VERIFICADO); su tokenizador e imagen cuentan distinto: comparar en
dólares por caso con el arnés de evals, no en tokens. Conclusiones: (a) la extracción determinista hace que el
Excel cueste ~10× menos que mandarlo entero; (b) **reducir fotos a 1024-1568 px** baja 2,7× el costo en modelos
de alta resolución sin perder las cotas (verificable con los casos FOT-01…04); (c) a escala del negocio
(p. ej. 30 documentos/mes) el costo de lectura es de centavos: lo caro es el contexto de herramientas.
(d) El dueño **aceptó** el nivel `-contributor` de Meta (bitácora, coordinador 2026-10-01: $0,10/$0,20 por MTok,
NO VERIFICADO, **entrena con los prompts**): los documentos de la tabla costarían 10-20× menos, pero el
motor debe marcar el **tipo de documento** para la regla por tarea que propone el coordinador: Excel de
proveedores, fotos de producto y catálogo → `-contributor` permitido; archivos con datos personales
(clientes, RUC, celulares, facturas de clientes, socios) → nivel sin entrenamiento o Claude. El lector ya
sabe detectarlo de forma determinista (columnas con rol `celular`/`ruc`/`cliente` = P1 en §9).

## 9. Lo que falta para que Brian sea «experto en Excel» (priorizado) y casos dorados

| Prioridad | Qué | Tamaño | Notas |
|---|---|---|---|
| **P0** | Integrar el lector como `leer_archivo` (contrato §6): en el Worker de r3-brian-agente o, mientras Brian siga en Odoo, en el Container como servicio (`POST /leer` con la clave de R2) | M | Reemplaza `_leer_adjunto` (`conversacion.py:480`) |
| **P0** | Normalizar imágenes antes del modelo (Images binding: ≤ 1568 px, JPEG/WebP, HEIC→JPEG) y dejar de rechazar > 5 MB | S | Arregla FOT-06 y las 54 PNG grandes |
| **P0** | Delimitador con nonce y `sospecha_instruccion` en la vista previa | S | Ya implementado en `src/modelo.ts` |
| **P0** | Correr los 33 casos nuevos + 26 de la ronda 2 con el arnés de evals (Claude y Meta) | S | `casos/dorado_documentos.jsonl` valida contra `esquema_caso.json` |
| P1 | `proponer/aplicar/deshacer_importacion` con `brian.importacion(.linea)` (llave, `antes`, origen celda) y `modo_itbms` obligatorio (D'CASA: `mas_itbms`, decisión del dueño 2026-10-01) | M | Lógica pura ya en `src/importacion.ts` |
| P1 | Clasificar el documento por sensibilidad (columnas celular/RUC/cédula/cliente/correo, facturas de clientes) para decidir el proveedor (Meta `-contributor` solo sin datos personales) y enmascarar antes de enviar | S | Regla por tarea del coordinador |
| P1 | Mapeo de columnas con modelo (`ESQUEMA_MAPEO` + `validarMapeo`) para encabezados raros | S | Solo columnas con rol null |
| P1 | `extraer_de_imagen` con esquema (medidas, precios de lista de proveedor, factura) y validación: foto → siempre confirmación | M | Casos FOT-01…05, ADV-05 |
| P1 | Conversión `.xls/.xlsb/.ods` en el Container (LibreOffice headless) | S | Aquí `soffice` no pudo abrir archivos en el sandbox (NO VERIFICADO en el Container) |
| P2 | Rendimiento: `DecompressionStream('deflate-raw')` nativo en vez de fflate y parser de atributos sin regex (perfil: 34 % tokenizador, 16 % inflate, 14 % atributos) | S | Bajaría el CPU de 50 MB por debajo de 30 s (estimado) |
| P2 | Evaluación de fórmulas sin caché (motor mínimo SUM/ROUND/IF) o recalcular en el Container | M | Hoy se reportan como `f_sin_cache` |
| P2 | Gráficos (`xl/charts`) → serie de datos; validaciones de datos (listas) y formato condicional | S | Encabezados «semánticos» |
| P2 | Tablas de Excel (`xl/tables/table*.xml`, ListObject) como señal fuerte de encabezado | S | Cuando existan |

### Casos dorados nuevos (33; amplían los 26 de la ronda 2)

Generados por `casos/generar_casos.ts` (verdad de terreno leída del fixture con el lector; fotos reales
verificadas a ojo): **XLI-01…06** (imágenes dentro del Excel: en celda, flotantes, ancla, alt, imagen que
cubre varias filas, Excel 365 real multi-`rc`), **XLE-01…13** (encabezado de 2 filas, valor+fórmula,
fórmula sin caché → null, filas ocultas, hoja oculta con costo para vendedor (crítico) y administrador,
segunda tabla, balboas con coma, precio por tamaño, «$—» → null (crítico), «Desde», comentario, conteo de
tablas, fecha serial), **CSV-01**, **DOC-01/02**, **PDF-01/02** (nativo y escaneado), **FOT-01…06** (fotos
reales de `up media/`: medidas en cm, W/D/H en inglés, variantes sin unidad, cinco cotas, «precio según la
foto» → null (crítico), foto de 9 MB), **ADV-04/05** (inyección en celda y en foto), **IMP-01** (importar
con `modo_itbms=mas_itbms` — decisión del dueño 2026-10-01 — y vista previa antes de aplicar).

Fotos revisadas (para la REFUTA de la bitácora): ALJ021439_1, ALJ021439_4, QMW020205_5, CZX100308_7,
1062010734-5-6N, LXI090407_2, DS090201_8, QMW020205_6, ALJ021439_2, CHCH010906, XXI070509_1,
COLCHON-FLEX-SEMIORTOPEDICO, N-F12002-K-BR_3, ZQ063601_1, ALJ021439_7, XLB0118616, LTSC-01-2806-K-BL_5,
XHT022-T-W_3: ninguna con precio impreso.

## 10. Fuentes

Oficiales:
1. Cloudflare Workers Limits — https://developers.cloudflare.com/workers/platform/limits/ (MCP, 2026-10-01).
2. Workers AI Markdown Conversion — how-it-works, conversion-options, binding: https://developers.cloudflare.com/workers-ai/features/markdown-conversion/ ; formatos: https://developers.cloudflare.com/ai-search/configuration/data-source/ ; changelog GIF/BMP 2026-07-08.
3. Workers AI Pricing — https://developers.cloudflare.com/workers-ai/platform/pricing/ (Last updated 2026-09-17).
4. Images binding — https://developers.cloudflare.com/images/optimization/binding/ (Last updated 2026-09-02); pricing https://developers.cloudflare.com/images/pricing/.
5. Skill oficial `workers-best-practices` (scratchpad `cf-skills/skills/workers-best-practices/`): stream, no bufferizar.
6. Claude Vision — https://platform.claude.com/docs/en/build-with-claude/vision (leída 2026-10-01).
7. Claude PDF support — https://platform.claude.com/docs/en/build-with-claude/pdf-support (leída 2026-10-01).
8. Precios Claude — skill `claude-api` (tabla «Current Models», caché 2026-09-25).
9. MS-XLSX «Local Image Type» / «Web Image Type» — https://learn.microsoft.com/en-us/openspecs/office_standards/ms-xlsx/aac1e2a6-7072-4e66-b1de-f20b8bf63318 (solo resumen del buscador; host bloqueado).
10. GitHub Advisories de SheetJS — GHSA-4r6h-8v6p-xvw6, GHSA-5pgg-2g8v-p4x9 (vía `npm audit`).

Proyectos / terceros:
11. dalmartin/xlcellimage (GPL-3) — https://github.com/dalmartin/xlcellimage, commit fa591235 (libros reales de Excel 365 y sus pruebas).
12. yfedoseev/office_oxide#302 — https://github.com/yfedoseev/office_oxide/issues/302 (cadena richData).
13. Skills `xlsx`, `pdf`, `docx` (Anthropic): dos cargas de openpyxl para valor+fórmula, `data_only` destructivo, `.xlsm` sin macros, «docx de terceros no es confiable», pdfplumber/OCR para escaneados.
14. Meta Model API — `ronda3/brian-agente.md` §2.3-2.4 (r3-brian-agente; dev.meta.ai bloqueado).

## 11. NO VERIFICADO

* Precio de la conversión de documentos (no imágenes) de `toMarkdown()`; que `toMarkdown` conserve algo de
  la estructura de celdas (no lo pude probar: no se crean recursos en la cuenta).
* `TextDecoder('windows-1252')` y `DecompressionStream('deflate-raw')` en el runtime de Workers (el
  prototipo no depende de ellos).
* Que el tope `--max-old-space-size=96 --max-semi-space-size=8` de Node equivalga al límite de 128 MB del
  isolate (aproximación razonable; la métrica oficial es el gráfico «Memory Usage» del dashboard).
* Precios y conteo de tokens de imagen de Meta Muse Spark.
* Cómo guardan LibreOffice y Google Sheets las imágenes en celda (no hay muestras; LibreOffice no abrió
  archivos en este sandbox).
* Valores de `CalcOrigin` (5 = «Colocar en celda» según los libros reales; el significado completo está en
  MS-XLSX, no leído).
