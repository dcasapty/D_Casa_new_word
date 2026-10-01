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

Convenciones: «mediana [mín-máx]» de 3 repeticiones salvo que se diga. Memoria en MiB. **PSS** reparte
las páginas compartidas entre procesos (es lo que suma de verdad en un contenedor con varios procesos);
el RSS de PostgreSQL sumado cuenta `shared_buffers` una vez por proceso y exagera. Odoo arrancado con
`odoo_run.sh` (misma config que `docker/entrypoint.sh`: `proxy_mode`, `unaccent`, `list_db=False`,
`limit_time_real=300`) contra el clúster propio 5441 (`pg_propio.sh`: `shared_buffers` indicado,
`work_mem=4MB`, `max_connections=40`). Público = visitante anónimo sin cookies; backend = sesión admin.

### 2.1 Memoria, arranque, latencia y CPU (script `campana.py`, crudos `res_campana.jsonl`, tabla `res_resumen_campana.txt` de `resumen.py`)

| Medida | Hilos `workers=0`, cron 1, `db_maxconn=64` (como entrypoint salvo maxconn) | Prefork `workers=2`, cron 1 |
|---|---|---|
| Arranque en frío → primer 200 en `/` (s) | 3,07 [2,96-3,21] | 3,05 [2,95-3,48] |
| Odoo en reposo (10 s tras arrancar) RSS / PSS | 169 / 150 | 601 / 228 (5 procesos) |
| Odoo caliente (sitio + backend admin + bundles) RSS / PSS | 216 / 197 | 667 / 405 |
| Odoo pico bajo carga 50 conc. PSS | 308 [300-325] | 428 [410-456] |
| PostgreSQL reposo / caliente PSS (shared_buffers 128MB) | 49 / 66 | 46 / 78 |
| PostgreSQL pico bajo carga 50 conc. PSS | 434 [422-450] (≈ 50 backends) | 89 [86-91] (≤ 6 backends) |
| **Pico total Odoo+PG PSS, 20 conc.** | **401 [401-451]** | **491 [483-517]** |
| **Pico total Odoo+PG PSS, 50 conc.** | **733 [729-773]** | **516 [494-546]** |
| Rendimiento 20 conc. (pet./s) | 12,9 [11,2-13,8] | 27,0 [26,9-27,2] |
| Errores 50 conc. (de 1000) | 0 | 9-18 (conexión cortada: `listen(8*workers)` = cola de 16, `vendor/odoo/odoo/service/server.py:1109`) |
| CPU media por petición bajo carga (mezcla 8 rutas) | 68 ms [64-80] | 49-50 ms [48-53] |

Con `db_maxconn=16` (valor de `docker/entrypoint.sh:43`): con 20 conc. 100/400 respuestas 500 y con 50 conc.
734/1000 respuestas 500, todas `psycopg2.pool.PoolError: The Connection Pool Is Full` (log `hilos_mc16_1.log`;
corrida previa con sesión compartida: 1 175 PoolError). Ver hallazgo H-1.

**Latencia secuencial con base caliente (una petición a la vez, 30 por ruta) y CPU por petición**
(`medir.py lat`, dentro de `campana.py`; hilos `db_maxconn=64`):

| Ruta | p50 ms | p95 ms | CPU ms/pet. (utime+stime de Odoo) | Prefork: p50 / CPU |
|---|---|---|---|---|
| `/` (anónimo) | 43 [41-64] | 70 [53-206] | 24,7 [23,7-38] | 38 / 25,7 |
| `/shop` | 238 [217-263] | 289 [245-370] | **174 [170-177]** | 203 / 160 |
| ficha de producto | 155 [143-191] | 177 [165-263] | 110 [101-114] | 145 / 113 |
| `/visitanos` | 39 [37-52] | 59 [53-89] | 27,7 [26-35] | 39 / 30 |
| `/web/login` | 43 [38-60] | 53 [48-134] | 26,7 [26-34] | 39 / 25 |
| `/socios` | 36 [35-56] | 48 [46-126] | 26,3 [26-37] | 38 / 26 |
| RPC lista de productos (80 filas, `web_search_read`) | 45 [43-49] | 59 [55-96] | 33 [31-47] | 40 / 32 |
| RPC lista de facturas (0 facturas en la base) | 9 [8-12] | 16 [10-453] | 6 [5-27] | 8 / 4,7 |

La misma `/` con sesión de admin cuesta ~114 ms de CPU y 128 ms p50 (corrida v1,
`res_campana_v1_maxconn16_sesion_compartida.jsonl`): el visitante logueado es 4-5× más caro que el anónimo.
`/shop` es la página cara (≈170 ms de CPU por visita: 20 productos con imágenes, filtros y precios).

**Bajo carga** (latencias de la mezcla, hilos): 20 conc. → p50 1,2-2,6 s; 50 conc. → p50 3-9 s y p95 hasta
18 s en `/shop`. Prefork w2, 20 conc. → p50 0,6-0,8 s, p95 0,7-0,9 s. Un solo proceso Python con hilos no
pasa de ~13 pet./s en esta máquina (GIL): el límite es la CPU de un núcleo, no la memoria.

### 2.2 Tamaño de la base (`tamano_base.sh`, crudo `res_tamano_base.txt`)

| Medida | Valor |
|---|---|
| Base `dcasa_test`/`r3_med_base` en el clúster principal | 211 MB (221 150 231 B) |
| Misma base recién restaurada (sin hinchazón) | 170 MB |
| `ir_attachment` (tabla + TOAST) | 120 MB; 2 425 adjuntos, 148 MB sin comprimir |
| · bundles JS/CSS (`ir.ui.view`, regenerables por Odoo) | 62 MB JS + 9,8 MB CSS |
| · fotos de productos (`product.template` 940 + `product.image` 675, JPEG) | 42 MB + 33 MB = 75 MB |
| Resto de la base sin `ir_attachment` | **≈ 91 MB** (la mayoría metadatos de Odoo: `ir_model_fields` 12 MB, `ir_ui_view` 9,9 MB, `ir_model_data` 7,8 MB) |
| Top 10 tablas | ir_attachment 120 MB · ir_model_fields 12 · ir_ui_view 9,9 · ir_model_data 7,8 · ir_module_module 3,6 · product_template 2,1 · ir_model_fields_selection 1,2 · ir_model_constraint 1,1 · ir_act_window 0,8 · ir_model 0,8 |

Con los adjuntos en almacenamiento de objetos (R2 vía `ir_attachment.location=file` + FUSE o un módulo
de almacenamiento S3), la base quedaría en ≈ 91 MB y R2 guardaría ≈ 75 MB de fotos (los bundles se
regeneran). Ojo: la base no tiene transacciones reales (0 facturas); el crecimiento real dependerá de
ventas, `mail_message` y PDF de facturas adjuntos.

### 2.3 Copia y restauración (`dump_restore.sh`, crudo `res_dump_restore.txt`; 5432 → 5441)

| Formato `pg_dump -Fc` | Tamaño | Dump (s) | Restore `-j1` (s) | Restore `-j4` (s) |
|---|---|---|---|---|
| gzip (por defecto) | 113,8 MB | 15,7 [15,1-17,3] | 24,5 [24,1-37,8] | 16,1 [13,9-26,0] |
| **zstd** | **109,0 MB** | **6,9 [5,3-7,0]** | 32,0 [29,3-41,6] | 17,6 [15,1-21,7] |
| lz4 | 199,7 MB | 3,0 [2,9-3,8] | – | – |
| sin compresión | 347,2 MB | 3,8 [3,7-4,8] | – | – |

El dump sin comprimir (347 MB) es mayor que la base (211 MB) porque `bytea` sale en hexadecimal y los
JS/CSS están comprimidos en TOAST. Casi todo el tamaño del dump son adjuntos (las fotos JPEG no comprimen).
`pg_dump` 16 trae zstd/lz4 integrados (no hace falta el binario `zstd`, que no está instalado).


## 3. Dimensionamiento recomendado
(pendiente)

## 4. Costos en Containers
(pendiente)

## 5. Lo que no pude medir
(pendiente)
