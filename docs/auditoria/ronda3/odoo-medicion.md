# Ronda 3 · r3-odoo-medicion — Odoo 19 medido de verdad

Fecha: 2026-10-01 · Agente: `r3-odoo-medicion` · Estado: **EN CURSO (informe incremental)**

Máquina de medición: 4 vCPU, 16 GB, Linux 6.18, Python 3.11.15, PostgreSQL 16 (paquete Ubuntu).
Otros agentes corren en paralelo: CPU y latencia tienen ruido (se repite ≥3 veces y se da mediana
y rango). La memoria (RSS/PSS de `/proc/<pid>/smaps_rollup`) es fiable.

Scripts reproducibles: `docs/auditoria/ronda3/odoo-medicion/` (cada cifra cita el script/comando).

## 0. Base medida
- `r3_med_base` = copia de `dcasa_test` (`createdb -T dcasa_test r3_med_base`, 8,3 s).
- 8 módulos `dcasa_*`/`website_dcasa` instalados, 108 módulos en total `state='installed'`.
- Catálogo real cargado: 199 `product.template` con xmlid de `dcasa_catalogo` (=199 entradas de
  `catalogo.json`), 202 plantillas en total, 230 variantes; 188 plantillas con `image_1920`.
- `ir_attachment.location = db`.

## 1. Resumen ejecutivo
(pendiente)

## 2. Mediciones
(se va llenando)

## 3. Dimensionamiento recomendado
(pendiente)

## 4. Costos en Containers
(pendiente)

## 5. Lo que no pude medir
(pendiente)
