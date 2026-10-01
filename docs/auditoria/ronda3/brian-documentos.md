# r3-brian-documentos (ronda 3): motor de lectura de documentos de Brian

Fecha: 2026-10-01. Agente: `r3-brian-documentos`. Solo escribe en `docs/auditoria/ronda3/`.
Prototipo: `docs/auditoria/ronda3/brian-documentos/` (TypeScript compatible con Workers, probado en Node 22).

> Informe incremental (regla de la ronda 3 tras el reinicio). Secciones marcadas «(en curso)» aún se están llenando.

## 1. Resumen ejecutivo (en curso)

## 2. Punto de partida (qué hace Brian hoy con adjuntos)

Sin cambios desde la ronda 2 (verificado hoy, 2026-10-01):

| Tema | Hoy | Evidencia |
|---|---|---|
| Lectura | Solo PDF con texto nativo (`PdfFileReader.extract_text`) y texto plano | `addons/dcasa_brian/models/conversacion.py:480-498` |
| `.xlsx` / `.docx` | «No puedo leer este tipo de archivo» | `conversacion.py:491` |
| `.xls` | Entra por `MIMES_TEXTO` y se decodifica como UTF-8 (basura) | `conversacion.py:89,487-489` |
| Imágenes | > 5 MB se rechazan sin redimensionar; solo la última imagen va al modelo | `conversacion.py:83,594-602` |
| Texto extraído | Recorte mudo a 20 000 caracteres | `conversacion.py:82,496-497` |
| Delimitador de datos | `<<DATOS …>>` / `<<FIN DE LOS DATOS>>` fijo (falsificable) | `conversacion.py:473-477` |
| Telegram | 10 MB por archivo; foto (la mayor) o documento | `models/telegram.py:45,188-204,383-402` |

## 3. Formatos y casos a cubrir

| Formato | Casos que el motor debe resolver | Estado en el prototipo |
|---|---|---|
| `.xlsx` / `.xlsm` | valores y fórmulas (con y sin caché, compartidas), combinadas, encabezados en varias filas, varias tablas por hoja, hojas/filas/columnas ocultas, formatos de número/moneda/fecha, comentarios (clásicos y en hilo), hipervínculos, imágenes **flotantes** (oneCell/twoCell/absolute) con celda ancla y texto alternativo, imágenes **en celda** (richData, «Colocar en celda» / `IMAGE()`), cuadros de texto, precios en texto, macros y vínculos externos (aviso, nunca se ejecutan) | **Hecho** (`src/xlsx.ts`, `src/tablas.ts`, `src/precios.ts`) |
| `.csv` / `.tsv` | UTF-8 con/sin BOM, UTF-16, **Windows-1252 con «;» y coma decimal** (como guarda Excel en español) | **Hecho** (`src/csv.ts`) |
| `.xls` (97-2003), `.xlsb`, `.ods` | convertir a xlsx en Container (LibreOffice / calamine) | Detección por firma; ruteo a Container (`src/firma.ts`, `src/documento.ts`) |
| xlsx/docx **con contraseña** | Es un contenedor OLE con `EncryptedPackage`, no un zip | Detectado y rechazado con mensaje claro |
| `.docx` | párrafos, tablas, imágenes en línea con texto alternativo | **Hecho** (`src/docx.ts`) |
| PDF | texto nativo por página; escaneado/foto → visión | **Hecho** el texto (unpdf); páginas sin texto se marcan `necesita_vision` (`src/pdf.ts`) |
| Fotos (fichas, listas de proveedores, facturas, notas a mano) | visión del modelo con salida estructurada validada; normalizar a JPEG/WebP ≤ 1568 px | Diseño (§6) + estimación de tokens (`src/imagenes.ts`) |

## 4. Evaluación de opciones y mediciones (en curso)
## 5. Prototipo (en curso)
## 6. Flujo completo para Brian (en curso)
## 7. Política ante inyección (en curso)
## 8. Costo en tokens por documento típico (en curso)
## 9. Lista priorizada para que Brian sea «experto en Excel» y casos dorados (en curso)
## 10. Fuentes (en curso)
## 11. NO VERIFICADO (en curso)
