# Ronda 4 · Costos que crecen y limpieza mensual («que no sea una bola de nieve»)

> Auditoría de solo lectura. Fecha: 2026-10-01. Pregunta del dueño: «Dijiste ~$12/mes. ¿En qué
> situaciones cuesta más? ¿Con cuántos clientes o facturas sube? Necesitamos depuración mensual: que lo
> borrado se borre completo, sin archivos huérfanos. Que los costos sean controlables.»
>
> Precios: buscador oficial de documentación de Cloudflare (MCP `search_cloudflare_documentation`,
> consultado hoy). Cifras de Odoo/PostgreSQL: mediciones de la ronda 3 (`ronda3/odoo-medicion.md`,
> `ronda3/datos.md`). Todo lo que es **supuesto** va marcado así; lo que no pude confirmar, **NO VERIFICADO**.

---

## 0. Respuesta corta para el dueño

1. **Los $12/mes son el piso y casi el techo del cómputo**, porque el contenedor `basic` tiene un tamaño
   fijo: aunque Odoo trabaje al 100 % las 24 h, el contenedor no puede pasar de **≈ $24/mes** (con el plan).
   No hay «cobro por cliente» ni «por factura».
2. **Lo único que lo vuelve bola de nieve es el tamaño de la base**, porque hoy los **PDF de facturas, fotos y
   archivos de Brian viven DENTRO de la base**. Con ~1 GB de base, el disco de 4 GB de `basic` ya no alcanza
   (imagen + base + WAL + volcado temporal) y hay que subir a `standard-1`: **de ≈ $13 a ≈ $34/mes** (salto ×2,7).
   A 10 ventas/día eso llega en **~2 años**; a 30 ventas/día con Brian activo, en **~1 año** (estimado, §3).
3. **R2 (respaldos) casi no cuesta**: aun con una base de 5 GB serían ≈ $3/mes. Las operaciones de R2 por el
   WAL de cada minuto usan ~10 % de lo gratis y **no pueden crecer más** (máximo un segmento por minuto).
4. **Riesgos de factura que sí pueden dispararse**: (a) **Brian sin tope de gasto** (no se registra el uso de
   tokens ni hay presupuesto; en abuso, cientos de dólares por hora); (b) **staging olvidado encendido**
   (+$4-8,5/mes, §2.6); (c) **tráfico de bots** muy alto (centavos a pocos dólares; el contenedor se satura antes).
5. **Lo borrado sí se borra**, pero no al instante en todas partes: desaparece de la base al momento, el
   espacio se reutiliza tras el `autovacuum`, y **sigue en los respaldos hasta 30 días** (8 días en pgBackRest,
   30 en los volcados diarios). No hay «archivos sueltos» porque los adjuntos son filas de la base; sí puede
   haber **filas huérfanas** de `ir_attachment` en casos concretos (§4.4).
6. **Facturas y contabilidad no se depuran nunca** (obligación legal; plazo exacto a confirmar con el contador,
   §4.6), ni el libro de Socios (regla del programa).

Plan de control (§5): alertas de presupuesto en Cloudflare ($10 y $20), tope de gasto de Brian, sacar los
archivos de la base hacia R2, depuración mensual de Brian/huérfanos/sesiones, reporte mensual de tamaños y
apagar staging cuando no se use.

---

## 1. Lo que ya está en el código (modelo de costo vigente)

| Pieza | Valor | Archivo |
|---|---|---|
| Contenedor | `basic` (1/4 vCPU, 1 GiB, 4 GB disco), `max_instances: 1`, ENAM | `edge/wrangler.jsonc:19-31` |
| Producción 24/7 | `ODOO_DORMIR_TRAS: ""` ⇒ `sleepAfter: "24h"` y `onActivityExpired` no apaga | `edge/wrangler.jsonc:52`, `edge/src/handler.ts:297-307`, `edge/src/index.ts:136-140` |
| Crons del Worker | `7 * * * *` (despierta si está apagado) y `17 8 * * *` (respaldo diario 03:17 Panamá). **El cron `*/10` ya no existe** | `edge/wrangler.jsonc:41`, `handler.ts:115-116` |
| Staging | mismo `basic`, `ODOO_DORMIR_TRAS: "1h"`, **mismo cron horario que lo despierta** | `edge/wrangler.jsonc:65-95` |
| WAL a R2 | `archive_timeout = 60`, vigilante `pg_switch_wal()` cada 60 s si el LSN avanzó, `archive-push` síncrono | `docker/pg.sh:239`, `:456-510` |
| pgBackRest | `repo1-retention-full-type=time`, `repo1-retention-full=7` (días), `repo1-bundle=y`, zstd 3, cifrado | `docker/pg.sh:140-153` |
| Respaldo físico | full si el último tiene ≥ 20 h (diario) o ≥ 24 h (auto); incr cada 6 h o tras restaurar | `scripts/respaldo.sh:60-70`, `docker/pg.sh:549-570` |
| Volcado lógico | `pg_dump -Fc zstd:3` cifrado → `pg_dump/` en R2, diario; **se escribe primero en disco local** y se sube; se borran los de **> 30 días** | `docker/pg.sh:573-616` |
| Adjuntos | `ir_attachment.location = db` (fotos, PDF, archivos de Brian dentro de PostgreSQL) | `addons/dcasa_base/__init__.py:204-207` |
| Sesiones | tabla `dcasa_http_session`; el autovacuum diario de Odoo borra las de > 7 días | `addons/dcasa_sesiones/almacen.py:207-221`, `vendor/odoo/odoo/addons/base/models/ir_http.py:404-408` |
| Logs | `observability.enabled: true` sin `head_sampling_rate`; Odoo `log_level = info`; PostgreSQL `log_checkpoints = on` | `edge/wrangler.jsonc:6`, `docker/entrypoint.sh:193`, `docker/pg.sh:244` |

Mediciones que usa este informe (ronda 3): base 211 MB (170 MB recién restaurada), `ir_attachment` 120 MB
(fotos 75 MB para 199 productos, bundles 71 MB), **≈ 91 MB sin adjuntos**; `pg_dump` zstd 109 MB; respaldo
pgBackRest 103 MB; RAM pico Odoo+PG ≈ 400 MiB (≈ 660 MiB PSS con 40 peticiones simultáneas); CPU por
petición 25 ms (`/`) a 174 ms (`/shop`), mezcla 68 ms; reposo ≈ 0,9 s CPU/h (Odoo) + 1,5 s/h (PG); WAL en
reposo: 59 segmentos/h, 3 peticiones S3 por segmento (LIST + GET + PUT), 0,7-8 KiB por segmento comprimido
(`ronda3/datos/salidas/reposo-*.txt`). Imagen Docker ≈ 1,3 GB (estimado en `docker/Dockerfile:71-80`).

---

## 2. Precios oficiales y costo por componente

### 2.1 Tarifas verificadas hoy

| Servicio | Incluido en Workers Paid ($5) | Excedente | Fuente |
|---|---|---|---|
| Containers memoria | 25 GiB-h/mes | $0,0000025/GiB-s (aprovisionada) | https://developers.cloudflare.com/containers/platform/pricing/ (Last updated 2026-08-28) |
| Containers CPU | 375 vCPU-min/mes | $0,000020/vCPU-s (**uso activo**) | ídem + changelog 2025-11-21 |
| Containers disco | 200 GB-h/mes | $0,00000007/GB-s (aprovisionado) | ídem |
| **Egress del contenedor** | **1 TB/mes (Norteamérica y Europa)** | $0,025/GB | ídem — **sí se cobra**, con 1 TB incluido |
| Workers solicitudes | 10 M/mes | $0,30/M | https://developers.cloudflare.com/workers/platform/pricing/ (2026-08-28) |
| Durable Objects | 1 M solicitudes, 400 000 GB-s | $0,15/M; $12,50/M GB-s | https://developers.cloudflare.com/durable-objects/platform/pricing/ (vía `ronda3/cf-plataforma.md` §3.2) |
| Workers Logs (incluye logs del contenedor) | **20 M eventos/mes**, 7 días | $0,60/M eventos | https://developers.cloudflare.com/workers/observability/logs/workers-logs/ ; contenedor: /containers/faq/ (2026-09-30) |
| Trazas (spans) | comparten los 20 M | **se cobran desde el 2026-10-01** | https://developers.cloudflare.com/workers/observability/traces/ |
| R2 almacenamiento | 10 GB-mes | $0,015/GB-mes (IA $0,01, mínimo 30 días) | /workers/platform/pricing/ (sección R2) |
| R2 Clase A (PUT, LIST, POST) | 1 M/mes | $4,50/M | ídem |
| R2 Clase B (GET, HEAD) | 10 M/mes | $0,36/M | ídem |
| R2 egress / DELETE | gratis | — | ídem |

Los incluidos son **por cuenta**: producción y staging los comparten.

### 2.2 Contenedor (lo que manda)

| Tipo | CPU media (fracción del vCPU del tipo) | Memoria | CPU | Disco | **Total con plan** |
|---|---|---|---|---|---|
| basic 24/7 | 3 % | 6,26 | 0,00 | 0,68 | **11,93** |
| basic 24/7 | 10 % | 6,26 | 0,85 | 0,68 | **12,78** |
| basic 24/7 | 25 % | 6,26 | 2,79 | 0,68 | **14,72** |
| basic 24/7 | 50 % | 6,26 | 6,03 | 0,68 | **17,96** |
| basic 24/7 | **100 % (techo físico)** | 6,26 | 12,51 | 0,68 | **24,44** |
| standard-1 24/7 | 10 % / 25 % | 25,70 | 2,14 / 6,03 | 1,40 | **34,24 / 38,13** |
| standard-2 24/7 | 10 % | 38,66 | 4,73 | 2,13 | **50,52** |

(Fórmulas de `ronda3/cf-plataforma/costos_containers.py`; recalculadas con
`max(0, recurso×segundos − incluido) × tarifa`.) **Clave para el dueño**: memoria y disco son fijos por tipo;
la CPU está acotada por el tamaño. Un mes de 1 000 o de 100 000 facturas cuesta casi lo mismo en `basic`; lo
que cambia el precio es **cambiar de tipo**.

Costo marginal de CPU por petición a Odoo: 68 ms × $0,00002 ≈ **$0,0000014** ⇒ 1 M de peticiones dinámicas ≈
**$1,36** (si cupieran; ver §3.3).

### 2.3 R2 (respaldos)

Lo que se guarda con la configuración actual (estimado: completos de pgBackRest ≈ 0,5× la base; volcado ≈ 0,5×):

- pgBackRest: ~8 completos (uno diario, retención 7 días) + incrementales + WAL de 7 días.
- Volcados lógicos: **30** (uno diario, borrado a los 30 días).
- ⇒ **R2 ≈ 40 × (tamaño comprimido de la base)** + WAL de una semana.

| Base comprimida (≈ base real) | R2 ocupado | Costo almacenamiento |
|---|---|---|
| 0,1 GB (hoy, 0,2 GB) | ≈ 4,3 GB | $0 |
| 0,25 GB (≈ 0,5 GB) | ≈ 10,2 GB | $0,01 |
| 0,5 GB (≈ 1 GB) | ≈ 20 GB | $0,16 |
| 1 GB (≈ 2 GB) | ≈ 40 GB | $0,45 |
| 5 GB (≈ 10 GB) | ≈ 198 GB | $2,82 |

Operaciones (supuesto peor: escritura cada minuto 24/7): 43 200 segmentos × (2 Clase A + 1 Clase B) +
~12 000 de respaldos + ~4 000 de revisiones horarias (`respaldo auto`: `info` + listado de volcados) ⇒
**≈ 100 000 Clase A (10 % de lo gratis)** y **≈ 50 000 Clase B + ~5 000 por cada restauración**. No puede
crecer: el vigilante corta **a lo sumo un segmento por minuto**; para pasar 1 M Clase A habría que escribir
~8 TB de WAL al mes. Las restauraciones (cada despliegue, reinicio de host o despertar de staging) suman
GET, muy lejos de 10 M. **Conclusión: R2 no es bola de nieve** (≈ $0,45/mes por cada GB comprimido de base).

### 2.4 Workers, Durable Objects, egress

- Cada petición no cacheada al sitio = 1 solicitud de Worker + **1 solicitud al Durable Object** del
  contenedor (`getContainer(...).fetch`, `edge/src/index.ts:237`). **El primer incluido que se agota es el de
  DO: 1 M/mes ≈ 33 000 peticiones dinámicas/día** (p. ej. ~6 600 visitas/día con 5 peticiones al origen c/u,
  **supuesto**). Excedente: $0,15 por millón: despreciable.
- Worker: 10 M/mes ≈ 330 000/día. Cuando el catálogo salga como Static Assets (Fase 2), esas visitas no
  cuentan (assets gratis e ilimitados, `ronda3/cf-plataforma.md` §3.1).
- DO del contenedor 24/7: 324 000 GB-s < 400 000 incluidos ⇒ $0 (lo comparte con futuros DO de Brian).
- **Egress del contenedor**: 1 TB/mes incluido. Lo usan las subidas a R2 por el endpoint S3 (full diario +
  volcado + WAL ≈ 2 × base comprimida/día ⇒ ~6 GB/mes hoy, ~30 GB/mes con base de 1 GB) y las llamadas de
  Brian al proveedor de IA. Si las respuestas a visitantes cuentan como egress: **NO VERIFICADO**; aun así,
  1 000 visitas/día × 3 MB ≈ 90 GB. Umbral lejano.

### 2.5 Logs / observabilidad (aviso del panel: 20 M eventos/mes)

Eventos por mes hoy (estimado): crons de Odoo con `log_level=info` (~280 ejecuciones/día × 2 líneas ≈ 17 000),
checkpoints de PostgreSQL (`log_checkpoints=on`, ≤ 2 líneas cada 5 min ≈ 17 000), 1 log de invocación del
Worker por petición + 1 línea de acceso de Odoo (werkzeug, nivel info) por petición dinámica. Con 1 000-3 000
visitas/día: **≈ 0,3-1 M eventos/mes (2-5 % del incluido)**. Se pasaría de 20 M solo con ~7-10 M peticiones
dinámicas/mes (bots). Excedente $0,60/M. **Supuesto NO VERIFICADO**: que cada línea de stdout/stderr del
contenedor sea un evento (la doc dice que se facturan «at the same rate», no cómo se cuentan).
Trazas: desde hoy cuentan como eventos; `wrangler.jsonc` no las activa (solo `observability.enabled`).

### 2.6 Staging: costo oculto encontrado

`env.staging` duerme tras 1 h sin visitas **pero el cron horario lo despierta** (`runScheduled` enciende si está
apagado, `handler.ts:95-102`). Secuencia: despierta a :07 → duerme ~:08 de la hora siguiente (el cron de esa
hora lo encuentra encendido) → despierta a :07 de la otra ⇒ **encendido ~50 % del tiempo (≈ 375 h/mes)**, con
una **restauración completa desde R2 cada ~2 h**. Como producción ya consume los incluidos:
**+$4,4/mes** (≈ 375 h) y **+$8,5/mes** si alguien lo deja en 24/7. Además sus respaldos ocupan el mismo
cupo gratis de R2 (cuenta). No es grave, pero **es el primer «gasto que nadie ve»**. (Cálculo de horas:
estimado a partir del código; no medido en la cuenta.)

### 2.7 IA de Brian (factura aparte del proveedor)

- Estimación previa: ≈ **$19/mes** a 50 interacciones/día con 80 % Meta (`DECISION_Y_PLAN.md`; precio de Meta
  **NO VERIFICADO**).
- Topes en código: `MAX_PASOS = 8` llamadas al modelo por mensaje, `MAX_TOKENS = 8000` de salida por llamada,
  historial ≈ 30 000 tokens, `MENSAJES_POR_MINUTO = 20` por usuario (`addons/dcasa_brian/models/conversacion.py:79-84`,
  `models/proveedores.py:54`).
- **No hay**: registro persistente del uso de tokens (el proveedor devuelve `uso` pero no se guarda:
  `proveedores.py:234-236,299-301`, sin escritura en `conversacion.py`), ni presupuesto diario/mensual, ni
  corte por gasto. Peor caso teórico por usuario: 20 mensajes/min × 8 llamadas × ~40 000 tokens de entrada
  ≈ 380 M tokens/h. **Es la única pieza con riesgo de factura sin techo.**
- Cloudflare AI Gateway ya ofrece **spend limits** (bloquea con 429 al pasar un presupuesto en $ por ventana;
  por modelo, proveedor o metadato como usuario; BYOK incluido) **solo para modelos con precio conocido**:
  https://developers.cloudflare.com/ai-gateway/features/spend-limits/ (Last updated 2026-09-30). Si Meta Muse
  Spark entra como proveedor personalizado sin precio, el límite podría no aplicarse: **NO VERIFICADO**.

---

## 3. Qué crece, cuánto y dónde están los umbrales

### 3.1 Bytes por registro (supuestos razonados sobre Odoo 19; medir en producción)

| Registro | Sin archivos | Archivos que hoy van a la base | Total aprox. |
|---|---|---|---|
| Cliente (`res.partner` + seguidores + mensaje de alta) | 3-6 KB | — | **~5 KB** |
| Venta completa (pedido + 3 líneas + entrega/movimientos + factura + asientos + pago + chatter) | 20-30 KB | PDF de factura guardado al imprimir/enviar (`invoice_pdf_report_id`) 40-120 KB; PDF de cotización si se envía por correo 40-100 KB; cuerpo HTML del correo 5-15 KB | **~100-250 KB** (≈ 150 KB típico) |
| Factura electrónica DGI (pendiente, Fase 0b) | — | XML firmado + PDF del PAC: 20-150 KB **NO VERIFICADO** | +? |
| Producto con fotos (medido: 75 MB / 199 productos, incluye 5 tamaños por imagen y galería) | ~10 KB | ~380 KB | **~0,4 MB** |
| Interacción con Brian (8 pasos, `crudo` = JSON completo del proveedor + resultados de herramientas hasta 12 000 caracteres) | 20-60 KB | archivos subidos: hasta 5 MB (imagen) / 10 MB (Telegram) **cada uno, sin depuración** | **~40 KB** + archivos |
| Sesión HTTP (`dcasa_http_session`) | ~1 KB | — | se borra a los 7 días |
| Visitante web / seguimiento | ~0,5 KB | — | se borra a los 60 días si no es cliente |
| Bundles JS/CSS (por despliegue) | — | ~70 MB que se reescriben (se borran los viejos) | estable, pero ~70 MB de WAL por despliegue |

### 3.2 Crecimiento anual de la base (estimado)

| Uso | Ventas/año | Brian/año | Fotos | **Base al año** |
|---|---|---|---|---|
| Bajo: 10 ventas/día, Brian 10 int./día | 3 650 × 150 KB ≈ 0,55 GB | 0,15 GB | 400 prod. ≈ 0,15 GB | **≈ 0,2 → 1,0 GB en ~1,5-2 años** |
| Medio: 30 ventas/día, Brian 50 int./día | ≈ 1,6 GB | ≈ 0,7 GB | 0,15 GB | **≈ 2,6 GB al año** |
| Mismo «Medio» con archivos fuera de la base (R2) | 30 × 25 KB ≈ 0,27 GB | ≈ 0,25 GB (sin `crudo` viejo) | 0 (en R2) | **≈ 0,6 GB al año** |
| 10 000 clientes adicionales | — | — | — | +50 MB (irrelevante) |

**Lectura**: los clientes no pesan; **los PDF y los archivos de Brian sí**. Cada 1 000 facturas con PDF ≈
0,15 GB de base; sin PDF en la base ≈ 0,025 GB.

### 3.3 Umbrales

| # | Umbral | Cuándo llega (estimado) | Qué pasa | Costo |
|---|---|---|---|---|
| a | **Disco de `basic` (4 GB)**: imagen 1,3 GB + datos ×1,2 (hinchazón) + `pg_wal` ≤ 0,3 GB + **volcado temporal** (`pg_dump` se escribe entero en `$PG_BASE/tmp` antes de subir) ⇒ base máx. ≈ **1 GB** | Bajo: ~2 años · Medio: **~4-5 meses** | El volcado diario o la restauración fallan por disco lleno; si R2 no responde, el WAL también llena el disco y PostgreSQL se detiene | Obliga a standard-1: **$34-38/mes** |
| a' | **RTO** (restaurar al arrancar/desplegar) | Crece lineal con la base: medido 46 s con 0,2 GB y S3 local; con R2 real **NO MEDIDO** (supuesto 1-3 min/GB) | Más minutos de 503 tras cada despliegue o reinicio de host | $0, pero el criterio de la Fase 1 es RTO < 5 min ⇒ ~2 GB es el límite práctico |
| a'' | RAM 1 GiB | No depende del tamaño de la base (`shared_buffers` fijo 128 MB); depende de usuarios simultáneos: ≈ 660 MiB PSS con 40 peticiones simultáneas | OOM ⇒ reinicio + restauración | standard-1 |
| b | **R2 > 10 GB gratis** | base comprimida ≈ 0,25 GB (≈ base real 0,5 GB) — **a los pocos meses en uso Medio** | Se empieza a pagar | **$0,16/mes con 1 GB de base**; $2,8 con 10 GB |
| c | **CPU de `basic` (1/4 vCPU)** | ~3 peticiones dinámicas/s sostenidas (68 ms de CPU c/u en un núcleo rápido; en 1/4 vCPU menos, **estimado**); `/shop` sin caché es lo caro | Lentitud (no factura extra: el techo es $24) | Para más rendimiento: standard-1 ($34-38) |
| d | DO 1 M solicitudes | ~33 000 peticiones dinámicas/día | $0,15/M | centavos |
| e | Logs 20 M eventos | ~7-10 M peticiones dinámicas/mes (bots) | $0,60/M | centavos-pocos $ |
| f | Workers 10 M solicitudes | ~330 000/día | $0,30/M | centavos |
| g | Egress 1 TB | base ≥ 10 GB o tráfico muy alto | $0,025/GB | centavos |

### 3.4 Tabla de escenarios → costo mensual (USD, con los $5 del plan, **sin la IA de Brian**)

| Escenario | Supuestos | Cloudflare/mes |
|---|---|---|
| **1. Hoy / arranque** | basic 24/7, CPU 3-10 %, base 0,2 GB, R2 ~4 GB, < 1 M peticiones | **$11,93-12,78** |
| 1b. + staging desplegado como está | durmiendo ~50 % (§2.6) / encendido 24/7 | **+$4,4 / +$8,5** |
| **2. Año 1 normal** | 10-30 ventas/día, 1 000-3 000 visitas/día, base 0,5-1 GB, CPU 10-25 % | **$12,8-15,2** (R2 $0-0,16) |
| **3. Base > ~1 GB con archivos dentro** (Medio a los ~5 meses, Bajo a los ~2 años) | standard-1 24/7, CPU 10-25 %, R2 20-40 GB | **$34,7-38,6** ← el salto evitable |
| 3b. Mismo volumen con archivos en R2 | basic, base < 1 GB por años, archivos en R2 (+0,5-2 GB × $0,015) | **$13-15** |
| **4. Odoo al 100 % de CPU en basic** (personal + visitas sin caché) | techo físico de basic | **$24,44** (máximo posible en basic) |
| 5. Bots: 10 M peticiones dinámicas/mes | DO +$1,35, logs ~$0-6, Worker $0; el contenedor se satura | **$24-31** (basic al tope) |
| 6. Base 10 GB (muchos años, archivos dentro) | standard-1 o mayor + R2 ~200 GB | **$37-55** |
| — Brian (aparte) | 50 interacciones/día | **≈ $19** (NO VERIFICADO) · **sin techo hoy** |

---

## 4. Retención y depuración: qué existe y qué falta

### 4.1 Respaldos en R2

| Qué | Estado | Detalle |
|---|---|---|
| Expiración de pgBackRest | **Existe** | `repo1-retention-full-type=time` + `repo1-retention-full=7` (`docker/pg.sh:151-152`). `pgbackrest backup` expira al terminar y borra el WAL que ya no hace falta. Ojo: con `type=time` se conservan los completos necesarios para volver a **cualquier momento de los últimos 7 días** (~8 completos + su WAL) |
| Poda de volcados lógicos | **Existe** | `respaldo_dump_podar` borra los de > `RESPALDO_DUMP_DIAS` (30) tras cada volcado (`docker/pg.sh:603-616`). Si el contenedor no corre, no poda (no crece tampoco) |
| Reglas de ciclo de vida de R2 | **Falta** (ni en `wrangler.jsonc` ni en `docs/`) | R2 aborta multipart incompletos a los 7 días por defecto (https://developers.cloudflare.com/r2/objects/upload-objects/). Se configuran con `wrangler r2 bucket lifecycle add <bucket> <nombre> <prefijo> --expire-days N` (https://developers.cloudflare.com/workers/wrangler/commands/r2/) |
| Copia anual de cierre (archivo legal) | **Falta** | Hoy no hay ningún respaldo de más de 30 días |
| Marcas de control `dcasa-control/pitr-aplicada-*` | Existe, nunca se borran | bytes; irrelevante |

### 4.2 Base de datos (Odoo y propios)

| Dato | Limpieza automática | Estado |
|---|---|---|
| Sesiones HTTP (`dcasa_http_session`) | autovacuum diario de Odoo → `PostgresSessionStore.vacuum`, > 7 días | **Existe** (`almacen.py:207-221`) |
| Visitantes web sin cliente | cron de Odoo, > 60 días (`website.visitor.live.days`) | **Existe** (Odoo, `website_visitor.py:334-360`) |
| Mensajes del bus, `res_device_log`, logs de usuario, notificaciones leídas (180 días), adjuntos perdidos del compositor de correo (> 1 día) | `@api.autovacuum` de Odoo | **Existe** (Odoo) |
| Correos salientes enviados (`mail.mail` con `auto_delete`) | se borran al enviarse | **Existe**; los fallidos se acumulan: **falta** |
| Bundles JS/CSS viejos | Odoo los borra al regenerar | **Existe** |
| Filestore GC (`_gc_file_store`) | **No aplica**: retorna sin hacer nada si el almacenamiento no es `file` (`vendor/odoo/odoo/addons/base/models/ir_attachment.py:190-194`) | — (con `location=db` no hay archivos en disco) |
| Conversaciones de Brian | Solo «archivar» (`activo=False`, sin interfaz) o borrar a mano en la lista; **nada automático**. `crudo` (JSON completo) se guarda en cada mensaje para siempre | **Falta** |
| Archivos subidos a Brian (chat/Telegram, `res_model='brian.conversacion'`) | Se van solo si se borra la conversación | **Falta** retención |
| Registro de acciones de Brian (`brian.accion`) | No se puede borrar por diseño (auditoría) | Correcto; vigilar tamaño de argumentos |
| Libro de Socios (`dcasa.movimiento`) | Nunca (regla 3 del programa) | Correcto |
| Contabilidad / facturas / sus PDF | Nunca (legal) | Correcto |
| Reporte de tamaños / costos | — | **Falta** |

### 4.3 ¿Lo borrado se borra completo? (ciclo de vida de un byte)

1. **Al borrar** (p. ej. una conversación de Brian o un producto): el ORM borra la fila y, en la misma
   transacción, **los `ir.attachment` con ese `res_model`/`res_id`** (`vendor/odoo/odoo/orm/models.py:4255-4264,4332-4333`).
   Los bytes viven en `ir_attachment.db_datas` (`bytea`/TOAST). **Odoo no usa *large objects*** de PostgreSQL
   (sin `lo_unlink`/`lo_import` en `vendor/odoo/odoo`): no hay riesgo de objetos grandes huérfanos.
2. **Minutos u horas después**: `autovacuum` (activo por defecto; `autovacuum_max_workers = 2`, `docker/pg.sh:225`)
   marca el espacio como libre y **se reutiliza** para filas nuevas. El archivo **no se encoge** sin
   `VACUUM FULL`, y los bytes viejos pueden seguir físicamente en páginas libres hasta que se sobrescriban.
3. **Respaldos**: el WAL que contenía el dato y los completos de pgBackRest anteriores al borrado viven
   **hasta 7-8 días** (luego `expire` los borra de R2). Los completos posteriores copian archivos enteros
   (podrían arrastrar páginas libres no sobrescritas, comprimidas). Los volcados lógicos (`pg_dump`) solo
   llevan filas vivas: el dato sale **del siguiente volcado**, pero los anteriores viven **hasta 30 días**.
4. **Fuera de nuestra base**: Workers Logs 7 días; el proveedor de IA (Meta en modo `-contributor` **entrena
   con lo enviado**: eso no se puede «des-enviar»); staging, si alguna vez se cargó con datos de producción.

⇒ **Borrado completo garantizado a los ~31 días** del borrado. Para un borrado «de privacidad» inmediato habría
que además: `VACUUM FULL` de la tabla, un respaldo completo nuevo y borrar a mano los completos/volcados
anteriores (rompe la ventana de vuelta atrás: decisión del dueño).

### 4.4 Riesgos de huérfanos (filas, no archivos)

- **Cascadas SQL**: cuando un padre se borra y los hijos caen por `ON DELETE CASCADE` de PostgreSQL, el ORM no
  ve a los hijos y **sus adjuntos quedan huérfanos**. Casos concretos: `brian.conversacion.usuario_id`
  (`ondelete='cascade'`, `conversacion.py:147-148`): borrar un usuario borra sus conversaciones en SQL y deja
  sus archivos (`res_model='brian.conversacion'`) huérfanos. Igual para cualquier modelo hijo con imágenes
  (p. ej. `product.image` si la plantilla los borra por cascada: **NO VERIFICADO** en el código de `product`).
- **Subidas sin enviar**: el chat de Brian sube el archivo antes del mensaje; si nunca se envía, queda con
  `res_id` vacío (`conversacion.py:210` solo asigna los que se envían). El autovacuum de Odoo solo limpia los de
  `mail.compose.message` (`vendor/odoo/addons/mail/wizard/mail_compose_message.py:699-713`), **no estos**.
- **SQL directo** en scripts o migraciones que borren filas sin pasar por el ORM.
- En R2 no hay huérfanos de respaldo previsibles (expire de pgBackRest + poda de volcados + aborto de multipart
  a 7 días). El archivo temporal del volcado se borra en éxito y en fallo (`pg.sh:573-600`); si el contenedor
  muere a mitad, el disco efímero desaparece con él.

### 4.5 PostgreSQL: hinchazón

`autovacuum` está activo (no se desactiva en `dcasa.conf`). No hay `VACUUM FULL` ni `pg_repack`
programados. Medido: 211 MB en uso vs 170 MB recién restaurada (**~20 % de hinchazón**). Cada restauración
desde R2 (cada despliegue o reinicio de host) la deja igual (copia física); el volcado lógico no la lleva.

### 4.6 Retención legal (no depurar)

- Facturas, asientos, pagos, sus PDF/XML y los libros: **conservar**. En Panamá el plazo habitual citado es
  **5 años** (Código de Comercio y normas de la DGI para factura electrónica) — **NO VERIFICADO: confirmar con el
  contador** antes de fijar cualquier política.
- Odoo ya impide borrar asientos publicados; la depuración mensual **no debe tocar** `account.*`, `dcasa.movimiento`,
  `brian.accion` ni los adjuntos con `res_model` contable.
- Los respaldos de 30 días **no son** el archivo legal; el archivo legal es la propia base viva + una copia
  anual de cierre (§5, punto 6).

---

## 5. Plan de «barandas de costo» (guardrails)

| # | Medida | Qué hace exactamente | Estado hoy | Dónde |
|---|---|---|---|---|
| 1 | **Alertas de presupuesto de Cloudflare** | Panel → *Manage Account* → *Billing* → *Billable Usage* → *Set Budget Alert* (o *Notifications* → *Budget Alert*). Varias alertas: **$10** y **$20** de gasto por uso (no incluye los $5 fijos). Desde 2026-06-15 Cloudflare crea una de **$10** por defecto. **Solo avisan por correo (al día siguiente); no cortan el servicio.** Fuente: https://developers.cloudflare.com/changelog/post/2026-04-13-billable-usage-dashboard-and-budget-alerts/ y /changelog/post/2026-06-15-budget-alerts-default-on/ | **Falta** (configurar en el panel; no es código) | `docs/OPERACION.md` «Cuánto cuesta» solo dice «revisar la factura» |
| 2 | **Tope de gasto de Brian** | (a) Guardar `uso` (tokens entrada/salida, proveedor, modelo) en cada `brian.mensaje`; (b) presupuesto diario y mensual en `ir.config_parameter` (p. ej. $2/día, $30/mes) que corte con mensaje amable al pasarse; (c) poner `BRIAN_BASE_URL` detrás de **AI Gateway** con *spend limits* por usuario y global (si Meta tiene precio conocido; si no, el tope propio (b) es el que vale); (d) límite de gasto también en la consola del proveedor | **Falta** (solo topes por mensaje: 8 pasos, 8 000 tokens, 20 msg/min) | `addons/dcasa_brian/models/proveedores.py`, `conversacion.py:79-84` |
| 3 | **Sacar los archivos de la base** (la palanca grande) | Adjuntos binarios nuevos (PDF, fotos, archivos de Brian) a R2; en la base queda solo la referencia. Opciones: OCA `fs_attachment` 19.0 (beta, `ronda3/datos.md` §5) o un módulo `dcasa_` propio que guarde en R2 (vía S3 firmado, como `r2_curl`). Mantiene la base < 1 GB por años ⇒ sigue en `basic` | **Falta** | `addons/dcasa_base/__init__.py:204-207` |
| 3b | Volcado en *streaming* | `pg_dump | openssl | subida` sin archivo temporal (multipart a R2) ⇒ el disco ya no necesita espacio para el volcado: sube el límite de base de `basic` de ~1 GB a ~2 GB | **Falta** | `docker/pg.sh:573-600` |
| 4 | **Depuración mensual** (cron de Odoo `dcasa_*`, día 1, 03:30 Panamá, con test) | (1) Brian: en conversaciones sin actividad > 90 días, vaciar `crudo` y recortar resultados de herramientas; borrar archivos subidos de > 30 días dejando el texto extraído (`datos_adjuntos`); borrar conversaciones archivadas > 180 días (plazos a decidir por el dueño). (2) Adjuntos huérfanos: por cada `res_model` de `ir_attachment`, borrar los que apuntan a un `res_id` inexistente o vacío con > 7 días, **excepto** modelos contables y de socios. (3) `mail.mail` en excepción > 90 días. (4) Sesiones anónimas (sin `uid`) > 1 día (las de usuarios siguen a 7 días). (5) Bajar `website.visitor.live.days` a 30. (6) `VACUUM (FULL, ANALYZE)` de `ir_attachment`, `brian_mensaje` y `dcasa_http_session` solo si su hinchazón > 30 % (bloquea la tabla segundos/minutos: madrugada). (7) Escribir el resumen en el log (`DCASA_LIMPIEZA borrados=… bytes_liberados=…`). Nunca toca `account.*`, `dcasa.movimiento`, `brian.accion` | **Falta** (solo existen los autovacuum de Odoo y el de sesiones) | nuevo en `addons/dcasa_base` o `dcasa_brian` |
| 5 | **Reglas de ciclo de vida en R2** | `pg_dump/` → expirar a **35 días** (red de seguridad si la poda del script falla; el script poda a 30). Todo el bucket → abortar multipart a 1 día. **No** poner reglas sobre `/pgbackrest` (pgBackRest gestiona su repositorio; borrar por fuera rompe la cadena de WAL). Staging: `pg_dump/` a 7 días | **Falta** | `docs/OPERACION.md` §2 (crear buckets) |
| 6 | **Copia anual de cierre** | Tras el cierre fiscal: un volcado con prefijo `archivo/AAAA/` (excluido de la poda), clase *Infrequent Access* ($0,01/GB-mes, mínimo 30 días). 5 años × ~1 GB ≈ $0,05/mes | **Falta** | `scripts/respaldo.sh` (modo nuevo) |
| 7 | **Reporte mensual de tamaños y costo** | El cron diario (o uno mensual) escribe una línea `DCASA_METRICA`: `pg_database_size`, top 10 tablas, `ir_attachment` por `res_model` (bytes), filas de sesiones, tamaño del repositorio (`pgbackrest info` da *repo size*), suma de volcados (listado con tamaños), tokens de Brian del mes; y avisa (`DCASA_ALERTA`) si la base pasa **0,7 GB** (prepararse para el 1 GB de `basic`) o R2 pasa 8 GB. Opcional: correo al admin | **Falta**; parcial: `respaldo.sh info` a mano, `/__edge/health` | `scripts/respaldo.sh`, `edge/src/index.ts` (`scheduled`) |
| 8 | **Staging bajo control** | Que el cron horario **no despierte staging** (o solo en horario de prueba) o eliminar el Worker `dcasa-staging` entre simulacros; poda de volcados de staging a 7 días | **Falta** (hoy ~+$4,4/mes) | `edge/wrangler.jsonc:65-95`, `edge/src/handler.ts:95-102` |
| 9 | Logs acotados | `--log-handler werkzeug:WARNING` (sin línea por petición) y `log_checkpoints = off` en producción; `head_sampling_rate` < 1 si llega tráfico de bots; no activar trazas sin necesidad (se cobran desde hoy) | Parcial (logs útiles, sin muestreo) | `docker/entrypoint.sh:193`, `docker/pg.sh:244`, `edge/wrangler.jsonc:6` |
| 10 | Bots fuera del contenedor | Regla de rate limiting del WAF (1 gratis) en `/shop` y `/web/login`; Fase 2: catálogo como Static Assets (gratis, no despierta ni carga Odoo) | Parcial (caché de estáticos en `edge/src/routing.ts`) | Fase 2 de `DECISION_Y_PLAN.md` |
| 11 | Retención/vuelta atrás de respaldos | pgBackRest 7 días + volcados 30 días | **Existe** | `docker/pg.sh:73-78,151-152,603-616` |
| 12 | Limpieza de sesiones, visitantes, bus, notificaciones | autovacuum de Odoo + `dcasa_sesiones` | **Existe** | §4.2 |

Orden sugerido: 1 y 2 (hoy, protegen la factura) → 8 (ahorra ~$4/mes ya) → 7 (ver el crecimiento real
antes de decidir) → 3/3b (antes de que la base pase ~0,7 GB) → 4, 5, 6.

---

## 6. Lo que no pude verificar

- Cómo cuenta Cloudflare los eventos de log del contenedor (¿uno por línea?) y si las respuestas del
  contenedor hacia el Worker cuentan como *egress*.
- Precio de Meta Muse Spark y si AI Gateway le aplica *spend limits* (requiere «precio conocido»).
- Tamaño real de los PDF de factura de D'CASA (fuentes Inter incrustadas + logo) y si el correo de la factura
  duplica el PDF como otro adjunto (en `location=db` no hay deduplicación por *checksum*).
- RTO con R2 real y tamaño real de la imagen en Cloudflare (los 1,3 GB son estimados del `Dockerfile`).
- Plazo legal de conservación en Panamá (contador).
- Las horas de staging (§2.6) salen de leer el código, no de la cuenta (no hay nada desplegado aún:
  `ronda3/cf-plataforma.md` §2).
