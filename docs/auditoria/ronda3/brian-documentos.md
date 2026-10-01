# r3-brian-documentos (ronda 3): motor de lectura de documentos de Brian

Fecha: 2026-10-01. Agente: `r3-brian-documentos`. Solo escribe en `docs/auditoria/ronda3/`.
Prototipo: `docs/auditoria/ronda3/brian-documentos/` (TypeScript compatible con Workers, probado en Node 22).

> Informe incremental (regla de la ronda 3 tras el reinicio). Secciones marcadas «(en curso)» aún se están llenando.

## 1. Resumen ejecutivo (en curso)

## 2. Punto de partida (qué hace Brian hoy con adjuntos)
Sin cambios desde la ronda 2 (verificado hoy): `addons/dcasa_brian/models/conversacion.py:480-498`
solo lee PDF con texto nativo (`PdfFileReader.extract_text`) y texto plano; `.xlsx`/`.docx` → «No puedo
leer este tipo de archivo» (`:491`); `.xls` entra por `MIMES_TEXTO` (`:89`) y se decodifica como UTF-8;
imágenes > 5 MB se rechazan (`:83,598`); texto recortado a 20.000 caracteres (`:82,496`). Telegram:
10 MB por archivo (`models/telegram.py:45,193`).

## 3. Formatos y casos a cubrir (en curso)
## 4. Evaluación de opciones y mediciones (en curso)
## 5. Prototipo (en curso)
## 6. Flujo completo para Brian (en curso)
## 7. Política ante inyección (en curso)
## 8. Costo en tokens por documento típico (en curso)
## 9. Lista priorizada para que Brian sea «experto en Excel» y casos dorados (en curso)
## 10. Fuentes
## 11. NO VERIFICADO
