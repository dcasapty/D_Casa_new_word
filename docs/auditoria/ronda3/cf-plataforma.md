# r3-cf-plataforma — Ficha oficial de Cloudflare y recálculo de costos (ronda 3)

Fecha: 2026-10-01 · Agente: `r3-cf-plataforma` · Solo lectura sobre la cuenta y el código.
Script de verificación: `docs/auditoria/ronda3/cf-plataforma/costos_containers.py` (salida en
`docs/auditoria/ronda3/cf-plataforma/salida_costos.md`).

**Método.** Todos los precios y límites de Cloudflare salen de `search_cloudflare_documentation`
(MCP oficial, documentación vigente) con URL y «Last updated» cuando el fragmento la trae. Cuatro
datos que el buscador del MCP no devolvió (D1 Time Travel y límites de D1, formatos de `toMarkdown`,
límites de Workers Builds) los leí del **repositorio fuente oficial** de la documentación
(`github.com/cloudflare/cloudflare-docs`, rama `production`, vía `raw.githubusercontent.com`), que es
lo que publica `developers.cloudflare.com`; lo marco **[repo docs]**. Lo que solo tengo de terceros va
marcado **[tercero]**. `developers.cloudflare.com` sigue bloqueado para WebFetch (no lo intenté rodear).

---

## 1. Resumen ejecutivo

1. **La cuenta está vacía** (2026-10-01, MCP): 0 Workers, 0 D1, 0 KV, 0 Hyperdrive, R2 activo con 0
   buckets. Nada se ha desplegado; no hay gasto en curso.
2. **El cambio a «CPU por uso activo» casi no mueve la factura de Odoo.** Lo que manda es la
   **memoria aprovisionada** (75-85 % del costo). Además, **las rondas 1-2 ya cobraban la CPU por uso
   activo** (al 10 %): `infra.md:384-388` y `ronda2/cf-costos.md` §4 lo dicen explícitamente. Las cifras
   de la ronda 2 eran correctas; las confirmo al centavo (standard-2 24/7, CPU 10 % = **$50,52/mes**
   con el plan). Lo que sí estaba mal en el resumen del coordinador era la premisa, no las cuentas.
3. **Odoo en Containers, con plan incluido** (CPU 3 % / 10 % / 25 %):

   | | basic (1 GiB) | standard-1 (4 GiB) | standard-2 (6 GiB, hoy) |
   |---|---|---|---|
   | 24/7 (720 h) | 11,93 / 12,78 / 14,72 | 32,42 / 34,24 / 38,13 | 46,89 / **50,52** / 58,29 |
   | Horario 12 h × 26 d (312 h) | 7,85 / 7,96 / 8,80 | 16,59 / 17,26 / 18,94 | 22,74 / 24,31 / 27,68 |
   | A demanda (155-290 h) | 6,28-8,48 | 10,63-17,91 | 13,58-26,03 |

   Más la base de datos (fuera de Containers; ver r3-datos) y lo que Brian gaste en modelos.
4. **Hoy el contenedor no puede dormir nunca**: el cron `*/10` (`edge/wrangler.jsonc:25`) hace
   `fetch` al contenedor (`edge/src/index.ts:97`) y «las peticiones entrantes reinician el temporizador
   automáticamente»; con `sleepAfter = "30m"` (`index.ts:51`) ⇒ **720 h/mes garantizadas**. Pasar a
   «a demanda» requiere quitar ese cron (o espaciarlo: cada 6 h con `sleepAfter` 10 min = 24 h/mes).
5. **«A demanda» tiene costos ocultos que no son dinero**: cada vez que duerme se pierden las
   sesiones de Odoo (se guardan en disco efímero: `vendor/odoo/odoo/http.py:995,2767-2770`), no corren
   los crons internos de Odoo, la primera visita espera el arranque de Odoo, y cualquier bot que pida
   una página no cacheada lo despierta.
6. **Todo lo que no es Odoo cabe en los $5** a la escala de D'CASA: sitio estático/borde, Brian por
   eventos (Workers + Durable Objects + Queues + Workflows), fotos en R2, respaldos en R2, logs, correo
   saliente (3 000/mes), 10 h/mes de navegador. Lo único que rompe el «casi nulo» es **un proceso Odoo
   corriendo** (memoria aprovisionada) y los **tokens del modelo**.
7. **Hechos que cambian diseños** (publicados temprano en la bitácora): isolate de Worker = 128 MB;
   Hyperdrive no soporta `LISTEN/NOTIFY`; D1 Time Travel 30 días (Paid) / 7 (Free); SIGTERM → 15 min →
   SIGKILL y reinicios de host irregulares; snapshots de Containers solo con policy `durable_object`
   (beta), atados a la imagen y TTL 30 días; tipos personalizados con mínimo 1 vCPU y 3 GiB/vCPU;
   `toMarkdown` lee **.xlsx/.xlsm/.xls/.docx/.pdf/imágenes** y es gratis salvo imágenes.

---

## 2. Inventario de la cuenta (MCP, solo lectura, 2026-10-01)

| Recurso | Herramienta | Resultado |
|---|---|---|
| Workers | `workers_list` | `{"workers":[],"count":0}` |
| D1 | `d1_databases_list` | 0 bases |
| KV | `kv_namespaces_list` | 0 namespaces |
| Hyperdrive | `hyperdrive_configs_list` | 0 configuraciones |
| R2 | `r2_buckets_list` | 0 buckets (R2 ya activado; sin error 10042) |

Otras herramientas de lectura del MCP (`workers_get_worker`, `workers_get_worker_code`,
`d1_database_get`, `kv_namespace_get`, `hyperdrive_config_get`, `r2_bucket_get`) necesitan un recurso
existente: no aplican. El MCP no expone lectura de plan/facturación, zonas, DNS, Containers ni Zero
Trust: **no pude verificar** si la cuenta ya tiene Workers Paid ni si `dcasapty.com` está en Cloudflare.
No creé, modifiqué ni borré nada.

---

## 3. Hechos oficiales (URL + Last updated)

### 3.1 Workers

Fuentes: https://developers.cloudflare.com/workers/platform/pricing/ (Last updated 2026-08-28) y
https://developers.cloudflare.com/workers/platform/limits/ (fecha no visible en el fragmento).

| | Workers Free | Workers Paid ($5/mes) |
|---|---|---|
| Solicitudes | 100 000/día | 10 M/mes incluidas + $0,30/M |
| CPU | 10 ms por invocación | 30 M ms/mes + $0,02/M ms; máx. 5 min por petición (defecto 30 s) |
| CPU por Cron | 10 ms | 30 s (intervalo < 1 h) / 15 min (≥ 1 h) |
| Duración (wall) | sin cargo | sin cargo |
| **Memoria por isolate** | **128 MB** | **128 MB** (incluye heap JS y WebAssembly) |
| Subsolicitudes | 50 externas / 1 000 a servicios CF | 10 000 por defecto, configurable hasta 10 M |
| Conexiones simultáneas salientes | 6 | 6 |
| Tamaño de script | 64 MiB sin comprimir | 64 MiB |
| Arranque global | 1 s | 1 s |
| Crons por cuenta | 5 | 250 |
| Static Assets | gratis e ilimitados; 20 000 archivos/versión, 25 MiB/archivo | gratis e ilimitados; 100 000 archivos/versión |

Notas: las subsolicitudes no se cobran; un WebSocket cuenta como 1 solicitud (los mensajes no). Si se
activa **Workers Caching**, las respuestas servidas desde esa caché (incluidos assets) se cobran como
solicitud (nota 4 de la página de precios). Existen **Python Workers** (ejemplo FastAPI:
https://developers.cloudflare.com/workers/languages/python/packages/fastapi/) — relevante para
r3-reconstruccion, pero con el mismo tope de 128 MB.

**Static Assets vs Pages**: la skill oficial (`cf-skills/skills/cloudflare/SKILL.md`) dice «Recommend
Workers and Workers Static Assets for new websites… Workers can do everything Pages can do». En Pages
también los assets son gratis (https://developers.cloudflare.com/pages/functions/pricing/, Last updated
2026-09-08). Para D'CASA: Workers + Static Assets.

### 3.2 Durable Objects

Fuente: https://developers.cloudflare.com/durable-objects/platform/pricing/ (Last updated 2026-09-30).

| | Free | Paid |
|---|---|---|
| Solicitudes (HTTP, RPC, mensajes WS a 20:1, alarmas) | 100 000/día | 1 M/mes + $0,15/M |
| Duración (se factura a 128 MB fijos) | 13 000 GB-s/día | 400 000 GB-s/mes + $12,50/M GB-s (redondeo al millón siguiente) |
| SQLite filas leídas | 5 M/día | 25 000 M/mes + $0,001/M |
| SQLite filas escritas | 100 000/día | 50 M/mes + $1,00/M |
| SQLite almacenamiento | 5 GB total | 5 GB-mes + $0,20/GB-mes |

- Objeto inactivo y apto para hibernar: **no paga duración**. Un WebSocket aceptado con `accept()`
  paga duración todo el tiempo; con la **API de hibernación** no. Una E/S pendiente puede mantenerlo en
  memoria hasta 15 min (mismo documento).
- **10 GB de SQLite por objeto** (changelog 2025-04-07 «SQLite in Durable Objects GA with 10GB»).
- **PITR: restaurar a cualquier punto de los últimos 30 días** (`getBookmarkForTime`,
  `onNextSessionRestoreBookmark`): https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/
  (Last updated 2026-09-21).
- Un DO 24/7 = 2 592 000 s × 0,125 GB = 324 000 GB-s: **cabe en lo incluido** (lo uso en el script
  como peor caso para el DO que controla el contenedor).

### 3.3 D1

- Precio (https://developers.cloudflare.com/workers/platform/pricing/, 2026-08-28): Free 5 M filas
  leídas/día, 100 000 escritas/día, 5 GB total; Paid 25 000 M leídas/mes + $0,001/M, 50 M escritas/mes +
  $1,00/M, 5 GB + $0,75/GB-mes. Sin egress. **Réplicas de lectura sin costo extra** (se paga igual por
  filas). Desde 2026-09-01 el plan Free **falla** al pasar el límite diario (changelog).
- Límites **[repo docs]** `src/content/docs/d1/platform/limits.mdx` (= /d1/platform/limits/): base máx.
  **10 GB (Paid) / 500 MB (Free)**; 50 000 bases (Paid) / 10 (Free); 1 TB por cuenta (Paid) / 5 GB (Free);
  1 000 consultas por invocación (Paid) / 50 (Free); consulta máx. 30 s; fila/BLOB máx. 2 MB.
- **Time Travel [repo docs]** `d1/reference/time-travel.mdx`: restaurar a cualquier punto **hasta 30
  días (Paid) / 7 días (Free)**. (El buscador del MCP no devolvió esta página; NO la vi renderizada.)

### 3.4 R2

Fuente: https://developers.cloudflare.com/r2/pricing/ (fecha no visible) y /workers/platform/pricing/.

| | Gratis/mes | Standard | Infrequent Access |
|---|---|---|---|
| Almacenamiento | 10 GB-mes | $0,015/GB-mes | $0,01/GB-mes (mínimo 30 días) |
| Clase A (PUT, LIST, multipart…) | 1 M | $4,50/M | $9,00/M |
| Clase B (GET, HEAD…) | 10 M | $0,36/M | $0,90/M |
| Recuperación | — | gratis | $0,01/GB |
| Egress a internet | gratis | gratis | gratis |

Redondeo al alza a la unidad siguiente (1,1 GB-mes ⇒ 2). DELETE gratis. La capa gratis **solo aplica a
Standard**. **Notificaciones de eventos** a Queues (`wrangler r2 bucket notification create … --event-type
object-create --queue …`): https://developers.cloudflare.com/r2/tutorials/upload-logs-event-notifications/
(Last updated 2026-08-25). API compatible con S3: la página de precios lista operaciones con nombres S3
(`PutObject`, `CompleteMultipartUpload`…); detalles de compatibilidad no los revisé.

### 3.5 KV, Queues, Workflows

Fuente: https://developers.cloudflare.com/workers/platform/pricing/ (2026-08-28).

- **KV**: Free 100 000 lecturas/día, 1 000 escrituras/borrados/listados/día, 1 GB. Paid 10 M lecturas +
  $0,50/M; 1 M escrituras + $5/M; 1 GB + $0,50/GB-mes.
- **Queues**: Free **10 000 operaciones/día**, retención 24 h fija (changelog 2026-02-04). Paid 1 M
  operaciones/mes + $0,40/M; retención 4 días (hasta 14). Operación = 64 KB; entregar un mensaje ≈ 3
  operaciones. Sin egress.
- **Workflows** (https://developers.cloudflare.com/workflows/reference/pricing/, Last updated 2026-09-21):
  CPU y solicitudes como Workers; Free 3 000 pasos/día y 1 GB; Paid 500 000 pasos/mes + $0,80/100 000 y
  1 GB-mes + $0,20/GB-mes. **No cobra CPU mientras espera una API o `step.sleep`**. Cobro de pasos y
  almacenamiento «desde el 10-ago-2026». Estado retenido 3 días (Free) / 30 días (Paid) por defecto.

### 3.6 Hyperdrive

- Precio (https://developers.cloudflare.com/hyperdrive/platform/pricing/): Free 100 000 consultas/día;
  Paid **ilimitadas**; pooling y caché sin cargo extra.
- Límites (https://developers.cloudflare.com/hyperdrive/platform/limits/): 10 configuraciones (Free) /
  25 (Paid); conexiones al origen **~20 (Free) / ~100 (Paid)**, mínimo 5; timeout de conexión inactiva
  10 min.
- Pooling **solo en modo transacción**
  (https://developers.cloudflare.com/hyperdrive/concepts/connection-pooling/, Last updated 2026-08-20).
- **No soporta**: `LISTEN`/`NOTIFY`, advisory locks, `PREPARE`/`DEALLOCATE` SQL, estado de sesión
  (https://developers.cloudflare.com/hyperdrive/reference/supported-databases-and-features/). La propia
  doc recomienda «un segundo cliente directo, sin Hyperdrive» para eso.
- ⇒ Odoo (bus con `LISTEN/NOTIFY`, psycopg2, advisory locks en crons) **no debe pasar por
  Hyperdrive**. Hyperdrive sirve para que **Workers** (Brian en el borde, sitio) lean un Postgres.
  No encontré documentación de un Container usando Hyperdrive (NO VERIFICADO).
- **Novedad (2026-06-18)**: se pueden crear **PlanetScale Postgres/MySQL facturados en la factura de
  Cloudflare**, a precio estándar de PlanetScale; «billed daily from when the database is created until
  deleted… whether or not you execute queries» (https://developers.cloudflare.com/hyperdrive/planetscale/).
  Precio de PlanetScale: fuera de mi alcance (r3-datos).

### 3.7 Containers (completo)

| Tema | Hecho oficial | Fuente |
|---|---|---|
| Cobro | cada 10 ms mientras corre; empieza al recibir petición o `start()`; para al dormir | /containers/platform/pricing/ (2026-08-28) |
| Incluido (Paid) | 25 GiB-h memoria, 375 vCPU-min, 200 GB-h disco | ídem |
| Excedente | $0,0000025/GiB-s, $0,000020/vCPU-s, $0,00000007/GB-s | ídem |
| Qué se mide | **memoria y disco: aprovisionado; CPU: uso activo** | ídem + changelog 2025-11-21 |
| Plan Free | no disponible | ídem |
| Egress | NA y Europa: 1 TB/mes incluido, luego $0,025/GB; Oceanía/Corea/Taiwán 500 GB y $0,05; resto 500 GB y $0,04 | ídem |
| Workers/DO/Logs | se cobran aparte con sus tarifas (cada contenedor tiene su DO) | ídem |
| Tipos | lite 1/16·256 MiB·2 GB; basic 1/4·1 GiB·4 GB; standard-1 1/2·4 GiB·8 GB; standard-2 1·6 GiB·12 GB; standard-3 2·8 GiB·16 GB; standard-4 4·12 GiB·20 GB | /containers/platform/limits/ (2026-09-30) |
| Tipos personalizados | mín. **1 vCPU**, máx. 4; máx. 12 GiB y 20 GB; **mínimo 3 GiB por vCPU**; sin ratio disco/memoria desde 2026-09-29 | ídem + changelog 2026-09-29 |
| Cuenta | 6 TiB memoria, 1 500 vCPU, 30 TB disco concurrentes (2026-02-25) | ídem |
| **Imagen** | **tamaño máx. = disco de la instancia** (basic: 4 GB); 50 GB de imágenes por cuenta | ídem |
| Snapshots | máx. 20 GB; retención 30 días desde creación o última restauración | ídem |
| Instancias | `max_instances` = máximo de instancias corriendo a la vez (las detenidas no cuentan) | /workers/wrangler/configuration/ |
| Ubicación | por defecto «la ubicación más cercana a la petición con la imagen ya descargada»; **`constraints.regions`**: ENAM, WNAM, EEUR, WEUR, APAC, SAM, ME*, OC*, AFR* (*capacidad limitada, no exclusivas); jurisdicción `eu`/`fedramp` | /containers/concepts/placement/ (2026-08-28) |
| DO y contenedor | «not guaranteed to run in the same location» | /containers/concepts/architecture/ |
| Arranque en frío | «often in the 1-3 second range», depende de imagen y entrypoint | /containers/faq/ |
| **Apagado** | **SIGTERM → espera hasta 15 min → SIGKILL**; igual en rollouts | /containers/concepts/architecture/ |
| **Host apagado** | «a host server restart happens on an irregular cadence. Cloudflare does not guarantee that any container instance will run for a set period»; tras el corte, la nueva instancia puede arrancar en otro servidor | /containers/faq/ |
| Duración máx. | no hay tope fijo de ejecución | ídem |
| `sleepAfter` | defecto 10 min; **las peticiones entrantes reinician el temporizador**; `renewActivityTimeout()` para trabajo en segundo plano | /containers/api/container-class/ |
| Disco | **efímero**: al dormir, la próxima arranca con disco limpio de la imagen | /containers/faq/ |
| Memoria | sin swap; OOM ⇒ reinicio | ídem |
| Scheduling policies | `default` (imagen y tipo en wrangler, rollouts) y `durable_object` (**beta pública**, desde 2026-09-30: imagen/tamaño en código, sin rollouts de app); **inmutable**: cambiarla = crear otra app y otro namespace de DO | /containers/configuration/scheduling-policy/ (2026-09-30) |
| **Snapshots** | beta; **solo con `durable_object`**; guardan el FS raíz escribible, **no memoria, procesos ni montajes**; atados a la versión de imagen; inmutables; TTL 30 días no configurable; la app decide cuándo guardar («changes made after the last snapshot exist only in the current instance»); no hay API para listarlos | /containers/guides/snapshots/ (2026-09-30), /sandbox/concepts/lifetime/ |
| FUSE a R2 | posible; «you should not expect native SSD-like performance» | /containers/faq/ |
| Salida a Workers | el contenedor puede llamar a Workers y bindings (KV, R2) por hostname (changelog 2026-03-26) | changelog |
| Registros | Cloudflare Registry, Docker Hub, ECR, Artifact Registry | /workers/wrangler/configuration/ |

**Sandbox SDK**: se factura exactamente como Containers + Workers + DO
(https://developers.cloudflare.com/sandbox/sdk/platform/pricing/, Last updated 2026-09-30). Útil para que
Brian ejecute Python (openpyxl, pdfplumber) en un contenedor efímero `lite`/`basic` solo mientras procesa
un archivo.

### 3.8 Workers AI, `toMarkdown`, AI Gateway, Browser Run

- **Workers AI** (https://developers.cloudflare.com/workers-ai/platform/pricing/, Last updated 2026-09-17):
  **$0,011 por 1 000 neuronas**; **10 000 neuronas/día gratis** en Free y Paid. Algunos modelos pesados
  exigen Paid (Kimi K2.6, GLM-5.2…; changelog).
- Modelos con **visión + tool calling** (catálogo /workers-ai/models/):
  `@cf/meta/llama-4-scout-17b-16e-instruct` (131 k contexto; $0,27/M entrada, $0,85/M salida) y
  `@cf/google/gemma-4-26b-a4b-it` (256 k contexto; visión con OCR, PDF, gráficos; function calling;
  disponible en Free). Calidad en español con las 45 herramientas de Brian: NO VERIFICADO (r3-brian-*).
- **`toMarkdown`** **[repo docs]** `partials/workers-ai/markdown-conversion-support.mdx`: **PDF; imágenes
  jpeg/jpg/png/webp/svg/gif/bmp; HTML; XML; `.xlsx .xlsm .xlsb .xls .et .docx`; `.ods .odt`; CSV;
  `.numbers`**. Precio **[repo docs]** `markdown-conversion/index.mdx`: «free for most format
  conversions»; las imágenes usan dos modelos de Workers AI (detección + descripción) y consumen neuronas.
  Opción `image.descriptionLanguage: "es"`. **No dice** si extrae las imágenes incrustadas en celdas de
  Excel: NO VERIFICADO (r3-brian-documentos debe probarlo).
- **AI Gateway** (https://developers.cloudflare.com/ai-gateway/reference/pricing/ y /limits/, ambas Last
  updated 2026-09-24): núcleo **gratis** (analítica, caché, rate limiting); DLP gratis; **Unified Billing:
  5 % de comisión sobre créditos**, tarifas del proveedor sin recargo; límite 200 solicitudes/60 s por
  gateway con credenciales gestionadas (no aplica a BYOK). Logs: cuentas que crean su **primer gateway
  desde 2026-09-24** siguen precio/retención de **Workers Logs**; caché: 25 MB por solicitud, TTL máx. 1
  mes; 10 gateways (Free) / 20 (Paid). **Fallback** con Dynamic Routing; **spend limits** por gateway.
  Opción `byok_only` para no caer en Unified Billing (changelog 2026-09-14).
- **Browser Run** (ex Browser Rendering): Free 10 min/día, 3 navegadores; Paid **10 h/mes** y 10
  concurrentes promedio incluidos, luego $0,09/h y $2/navegador concurrente
  (https://developers.cloudflare.com/browser-run/limits/, Last updated 2026-09-26; changelog 2025-07-28).

### 3.9 Images, caché, seguridad, correo, secretos, observabilidad, builds

- **Images** (https://developers.cloudflare.com/images/pricing/, dateModified 2026-07-08): plan Images Free
  = **5 000 transformaciones únicas/mes** sobre imágenes en R2 u origen propio; al pasarse, las nuevas
  devuelven error 9422 (no cobra). Images Paid: $0,50/1 000 transformaciones extra; almacenamiento $5/100 000
  imágenes; entrega $1/100 000. El binding se cobra por transformación única desde 2026-07-01.
- **Caché**: **todas las purgas (URL, host, prefijo, tag, todo) en todos los planes**, incluido Free
  (changelog 2025-04-01; https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-tags/, Last
  updated 2026-08-21). **Cache Reserve** requiere plan de pago y cuesta como R2 ($0,015/GB-mes, A $4,50/M,
  B $0,36/M) (/cache/advanced-configuration/cache-reserve/). Tiered Cache: los Static Assets la usan
  automáticamente (/workers/static-assets/); disponibilidad de Smart Tiered Cache por plan: NO VERIFICADO.
- **WAF / rate limiting en Free** (https://developers.cloudflare.com/waf/rate-limiting-rules/): **1 regla**,
  características fijas a IP, periodo y bloqueo de **10 s**, acción Block. Suficiente para `/web/login`
  o `/socios` como freno básico, no como defensa fina.
- **Turnstile** (https://developers.cloudflare.com/turnstile/plans/, Last updated 2026-08-14): gratis,
  hasta 20 widgets por cuenta.
- **Zero Trust**: Tunnel conecta un servidor sin abrir puertos (https://developers.cloudflare.com/tunnel/).
  «Tunnel gratis» y «Access gratis hasta 50 usuarios» los confirman solo **[tercero]** (costbench,
  zerometric, recca0120; 2026); el buscador del MCP no devolvió la página de planes.
- **Email Service** (https://developers.cloudflare.com/email-service/platform/pricing/): Email Routing
  entrante ilimitado en ambos planes; **envío a cualquier destinatario solo en Paid: 3 000 correos/mes
  incluidos, luego $0,35/1 000**; envío a direcciones verificadas gratis. Mensaje entrante máx. 25 MiB.
- **Secrets Store** (https://developers.cloudflare.com/secrets-store/manage-secrets/, Last updated
  2026-09-25): beta, **100 secretos por cuenta**, 1 almacén, secreto ≤ 64 KiB; precio no publicado.
- **Workers Logs** (https://developers.cloudflare.com/workers/observability/logs/workers-logs/): Free
  200 000 eventos/día, 3 días; Paid **20 M/mes + $0,60/M, 7 días**. Logpush: 10 M/mes + $0,05/M (Paid).
  Los logs del contenedor van al mismo sistema y tarifa.
- **Workers Builds** **[repo docs]** `workers/ci-cd/builds/limits-and-pricing.mdx`: Free 3 000 min/mes, 1
  build concurrente; Paid 6 000 min/mes + $0,005/min, 6 concurrentes; timeout 20 min; 8 GB RAM; 20 GB disco.
  El repo ya despliega con GitHub Actions; no es necesario.

---

## 4. Recálculo de Odoo en Containers (CPU por uso activo)

### 4.1 Fórmulas (script `costos_containers.py`)

Por mes de 720 h y para `s` segundos activos:
- memoria = max(0, GiB × s − 90 000) × 2,5e-6
- CPU = max(0, vCPU × uso × s − 22 500) × 2e-5
- disco = max(0, GB × s − 720 000) × 7e-8
- DO del contenedor = 0,125 GB × s; incluido 400 000 GB-s (nunca se supera con 1 instancia)
- total = contenedor + DO + $5 del plan. Sin base de datos, sin modelos de IA, sin egress (1 TB
  incluido en Norteamérica sobra para D'CASA).

**No usé mediciones de r3-odoo-medicion**: al cerrar este informe no había publicado memoria real ni
CPU por petición en la bitácora. El uso de CPU es supuesto (3/10/25 % del vCPU aprovisionado).

### 4.2 Horas activas por patrón (supuestos explícitos)

- **24/7**: 720 h. Es el caso actual, forzado por el cron (4.4).
- **Horario comercial**: 12 h × 26 días = 312 h. Requiere encender/apagar (cron a las 7:00 y
  `stop()` a las 19:00) y que nada lo despierte de noche.
- **A demanda** (contenedor duerme de verdad, sin cron de 10 min): cada despertar cuesta actividad +
  `sleepAfter`. Supuestos: personal 4 ráfagas/día de 45 min durante 26 días; sitio/bots 10 despertares/día
  de 2 min durante 30 días. Resultado: **155 h (sleepAfter 10 min), 189 h (15 min), 290 h (30 min)**. Si
  las visitas no cacheadas llegan con menos separación que `sleepAfter`, converge a 24/7.

### 4.3 Resultado (USD/mes con los $5 del plan)

| Patrón | Horas | Tipo | CPU 3 % | CPU 10 % | CPU 25 % | memoria | disco |
|---|---|---|---|---|---|---|---|
| 24/7 | 720 | basic | 11,93 | 12,78 | 14,72 | 6,26 | 0,68 |
| 24/7 | 720 | standard-1 | 32,42 | 34,24 | 38,13 | 25,70 | 1,40 |
| 24/7 | 720 | standard-2 | 46,89 | **50,52** | 58,29 | 38,66 | 2,13 |
| Horario 12×26 | 312 | basic | 7,85 | 7,96 | 8,80 | 2,58 | 0,26 |
| Horario 12×26 | 312 | standard-1 | 16,59 | 17,26 | 18,94 | 11,01 | 0,58 |
| Horario 12×26 | 312 | standard-2 | 22,74 | 24,31 | 27,68 | 16,62 | 0,89 |
| A demanda, sleep 10 min | 155 | basic | 6,28 | 6,28 | 6,53 | 1,17 | 0,11 |
| A demanda, sleep 10 min | 155 | standard-1 | 10,63 | 10,74 | 11,58 | 5,37 | 0,26 |
| A demanda, sleep 10 min | 155 | standard-2 | 13,58 | 14,25 | 15,93 | 8,16 | 0,42 |
| A demanda, sleep 15 min | 189 | basic | 6,62 | 6,62 | 7,02 | 1,48 | 0,14 |
| A demanda, sleep 15 min | 189 | standard-1 | 11,91 | 12,14 | 13,16 | 6,58 | 0,33 |
| A demanda, sleep 15 min | 189 | standard-2 | 15,50 | 16,41 | 18,45 | 9,98 | 0,52 |
| A demanda, sleep 30 min | 290 | basic | 7,63 | 7,70 | 8,48 | 2,39 | 0,24 |
| A demanda, sleep 30 min | 290 | standard-1 | 15,75 | 16,34 | 17,91 | 10,22 | 0,53 |
| A demanda, sleep 30 min | 290 | standard-2 | 21,44 | 22,90 | 26,03 | 15,44 | 0,83 |

Ejemplo paso a paso (standard-2, 24/7, CPU 10 %): s = 2 592 000. Memoria (6 × 2 592 000 − 90 000) =
15 462 000 GiB-s × 2,5e-6 = **$38,66**. CPU (1 × 0,10 × 2 592 000 − 22 500) = 236 700 × 2e-5 = **$4,73**.
Disco (12 × 2 592 000 − 720 000) = 30 384 000 × 7e-8 = **$2,13**. DO 324 000 GB-s < 400 000 = $0. Total
$45,52 + $5 = **$50,52** (idéntico a `ronda2/cf-costos.md` §4.1).

**Lectura**: la memoria es 75-85 % del costo 24/7. Pasar de CPU 3 % a 25 % sube standard-2 solo $11,40.
Lo que de verdad baja la factura es (a) **menos GiB aprovisionados** y (b) **menos horas encendido**.
Lo incluido se agota rápido: standard-1 consume sus 25 GiB-h de memoria en **6,25 h**, standard-2 en
**4,17 h**, basic en **25 h**.

### 4.4 El cron del Worker: cuantificado

`edge/wrangler.jsonc:25` (`"*/10 * * * *"`) + `edge/src/index.ts:96-98` (`fetch` a `/web/health`) +
`sleepAfter = "30m"` (`index.ts:51`). Como «Incoming requests reset the timer automatically»
(https://developers.cloudflare.com/containers/api/container-class/), el intervalo (10 min) es menor que
`sleepAfter` (30 min) ⇒ **nunca duerme: 720 h**. Aunque se bajara `sleepAfter` a 10 min, empataría con
el cron y seguiría despierto.

Horas que un cron, **por sí solo**, mantiene despierto el contenedor (supuesto: 1 min de arranque + 1 min
de trabajo por disparo):

| Intervalo del cron | sleepAfter 10 min | 15 min | 30 min |
|---|---|---|---|
| 10 min (hoy) | 720 | 720 | 720 |
| 30 min | 288 | 408 | 720 |
| 60 min | 144 | 204 | 384 |
| 3 h | 48 | 68 | 128 |
| 6 h | 24 | 34 | 64 |
| 24 h | 6 | 8,5 | 16 |

En dinero (standard-2, CPU 10 %): cron actual **$50,52**; cada hora con sleep 10 min **$13,52**; cada 6 h
**$6,09**; una vez al día **$5,10**. El cron de hoy cuesta, frente a «a demanda» con sleep 15 min, unos
**$34/mes** de más en standard-2 (50,52 − 16,41) o **$22** en standard-1 (34,24 − 12,14).

Costo del cron en el Worker (no en el contenedor): 4 320 invocaciones/mes, despreciable frente a 10 M.

### 4.5 Lo que «a demanda» rompe en Odoo (no es dinero, pero pesa)

1. **Sesiones**: Odoo guarda las sesiones en disco (`FilesystemSessionStore` en
   `vendor/odoo/odoo/http.py:995` y `session_dir` en `:2767-2770`; `data_dir=/var/lib/odoo/data` en
   `docker/entrypoint.sh`). El disco del contenedor es efímero ⇒ **cada vez que duerme, se reinicia el host
   o se despliega, todos quedan deslogueados** y los carritos anónimos se pierden. Pasa también en 24/7 con
   cada despliegue o reinicio de host, pero a demanda pasa varias veces al día.
2. **Crons internos de Odoo** (`max_cron_threads=1`, `docker/entrypoint.sh:43`): con el contenedor dormido
   no corren. Habría que dispararlos desde el Worker con un cron espaciado (cada 1-6 h según la tabla 4.4).
3. **Arranque**: la plataforma da 1-3 s típicos, pero la primera respuesta depende del arranque de Odoo
   (cargar registro de 108 módulos según r3-reconstruccion). No medido por mí; r3-odoo-medicion.
4. **Bots**: cualquier página no cacheada lo despierta. r3-sitio-edge midió (bitácora, 2026-10-01) que el
   HTML de Odoo **no se puede cachear tal cual** (`Set-Cookie: session_id` y `csrf_token` atado a la sesión
   en cada página), así que hoy **toda visita al sitio despierta Odoo**. Solo si el sitio sale de Odoo
   (Static Assets en el borde) Odoo lo despiertan únicamente el personal y Brian; sin eso, «a demanda»
   converge a 24/7 en cuanto hay tráfico real.
5. **basic (1 GiB)** solo sirve si Odoo + 1 hilo de cron caben medidos en 1 GiB sin OOM, y si la imagen
   pesa **≤ 4 GB** (tamaño máx. de imagen = disco de la instancia). Ambas cosas: NO VERIFICADAS.

---

## 5. Qué cabe gratis dentro de los $5 (Workers Paid) para D'CASA

| Uso de D'CASA | Servicio | Incluido en Paid | Uso estimado (supuesto) | Desde dónde cuesta |
|---|---|---|---|---|
| Sitio público estático (catálogo 199 productos, HTML/CSS/JS) | Static Assets | **ilimitado y gratis** | todo | nunca (salvo Workers Caching activo) |
| Sitio dinámico / proxy / API | Workers | 10 M solicitudes, 30 M ms CPU | < 0,3 M/mes | > 10 M solicitudes/mes: $0,30/M |
| Brian por eventos (estado, conversación) | Durable Objects | 1 M solicitudes, 400 000 GB-s, 5 GB SQLite | ≈ 7 500-225 000 GB-s (50-1 500 interacciones/día, `ronda2/brian-eventos.md` §5.2, tarifas reconfirmadas) | ≈ 2 700 interacciones/día con 5 GB-s c/u |
| Brian: tareas largas (Excel, PDF) | Workflows | 500 000 pasos, 1 GB | < 30 000 pasos | > 500 000 pasos: $0,80/100 000 |
| Colas (eventos de Odoo, archivos subidos) | Queues | 1 M operaciones (≈ 333 000 mensajes) | < 50 000 | > 333 000 mensajes/mes |
| Datos ligeros del borde (catálogo, socios en caché) | D1 | 5 GB, 25 000 M lecturas, 50 M escrituras; Time Travel 30 días | < 1 GB | > 5 GB: $0,75/GB-mes |
| Configuración/caché | KV | 10 M lecturas, 1 M escrituras, 1 GB | mínimo | — |
| Fotos de productos | R2 | 10 GB, 1 M clase A, 10 M clase B, egress gratis | 199 × 5 fotos × 0,5 MB ≈ 0,5 GB (supuesto) | > 10 GB: $0,015/GB-mes |
| Variantes de fotos | Images (plan Images Free) | 5 000 transformaciones únicas/mes | 199 × 5 × 3 tamaños ≈ 2 985 | > 5 000: hace falta Images Paid ($0,50/1 000) |
| Respaldos de la base | R2 | dentro de los 10 GB | p. ej. 23 copias ≤ 0,4 GB | > 10 GB acumulados |
| Lectura de documentos | `toMarkdown` | gratis (salvo imágenes) | — | imágenes: neuronas |
| IA en Cloudflare | Workers AI | 10 000 neuronas/día | depende del modelo | > 10 000/día: $0,011/1 000 |
| IA externa (Meta, Claude…) | AI Gateway | núcleo gratis; logs según Workers Logs | — | 5 % si se usan créditos de Unified Billing; BYOK sin recargo |
| Correo saliente | Email Service | 3 000/mes | facturas, avisos | > 3 000: $0,35/1 000 |
| PDF/capturas del sitio | Browser Run | 10 h/mes | — | $0,09/h |
| Logs | Workers Logs | 20 M eventos, 7 días | < 1 M | > 20 M: $0,60/M |
| Antibots | Turnstile | gratis (20 widgets) | 2-3 | — |
| Odoo (proceso Python) | Containers | 25 GiB-h memoria, 375 vCPU-min, 200 GB-h | 720 h × 4-6 GiB | **a las 4-25 h/mes** según tipo (4.3) |

Conclusión: **todo lo del borde y Brian cabe en los $5 con margen de 10-100×**; el único gasto que no cabe
es **mantener Odoo encendido** (y la base de datos, que no vive en Cloudflare).

---

## 6. Nota para el dueño: plugin oficial de Cloudflare para Claude Code

Fuente: https://developers.cloudflare.com/agent-setup/claude-code/ (consultada vía MCP, 2026-10-01).

1. Abrir Claude Code en la raíz del proyecto donde está `edge/wrangler.jsonc` (o en `edge/`).
2. Escribir, dentro de Claude Code:
   ```
   /plugin marketplace add cloudflare/skills
   /plugin install cloudflare@cloudflare
   ```
3. La primera vez que Claude use una herramienta de Cloudflare, se abre el navegador para autorizar con
   OAuth y elegir permisos (empezar con permisos de solo lectura). Para CI se usa un API token.
4. Verificar con `claude mcp list`.

Qué aporta: (a) **Skills** de Cloudflare (Workers, Durable Objects, Agents SDK, wrangler, Containers…)
como contexto permanente; (b) el **MCP de la API de Cloudflare** en «Code Mode» (2 herramientas,
`search()`/`execute()`, que cubren 2 500+ endpoints: DNS, WAF, R2, Zero Trust…) y los MCP por producto,
incluida la documentación vigente; (c) comandos `/cloudflare:build-agent` y `/cloudflare:build-mcp`.
Riesgo: el MCP de API puede **crear y borrar** recursos; conviene un token o permiso OAuth de lectura y
pedir confirmación antes de cualquier escritura. Alternativa sin plugin: `developers.cloudflare.com/llms.txt`.

---

## 7. Recomendación

1. **Quitar el cron `*/10` o espaciarlo a ≥ 1 h** antes de desplegar nada; es la palanca más grande
   ($22-34/mes). Disparar desde el Worker solo los trabajos de Odoo que de verdad deban correr sin
   personas (puntos de socios, correo), con `sleepAfter` de 10 min.
2. **Elegir el tamaño por memoria medida**, no por vCPU: si Odoo cabe en 1 GiB (basic) el piso es
   ≈ $6-13/mes; si necesita 4 GiB (standard-1), ≈ $11-34/mes según horas. standard-2 solo si la
   medición lo exige. Los tipos personalizados no bajan de 1 vCPU/3 GiB: no abaratan.
3. **Servir el sitio desde el borde** (Static Assets + caché con purga por tag, gratis en todos los
   planes) para que los visitantes y bots no despierten Odoo. Es lo que vuelve viable «a demanda».
4. **Brian en el borde** (Workers + DO con hibernación + Workflows + Queues + AI Gateway BYOK + `toMarkdown`)
   cabe en los $5; Odoo queda como ejecutor de herramientas, despertado solo cuando hace falta.
5. **No poner PostgreSQL dentro de un Container** (disco efímero; snapshots beta, solo policy
   `durable_object`, atados a la imagen, sin consistencia de base en marcha; reinicios de host sin aviso).
   **No pasar Odoo por Hyperdrive** (sin `LISTEN/NOTIFY`).
6. Si se va a demanda: mover las **sesiones de Odoo fuera del disco** (base de datos o R2) — decisión de
   r3-reconstruccion/r3-odoo-medicion; sin eso, cada siesta desloguea a todos.
7. Fijar `constraints.regions: ["ENAM"]` en el contenedor para acercarlo a Panamá y a la base
   (latencia no medida).

Comparación honesta con la ronda 2: un VPS único con Tunnel seguía en ≈ $12-17/mes con base persistente
incluida. Odoo en Containers solo le gana en precio si es **basic a demanda** (≈ $6-8 + base aparte), y lo
hace a costa de sesiones perdidas y arranques en frío.

---

## 8. Lo que no pude verificar

- Si la cuenta ya está en **Workers Paid** y si `dcasapty.com` está en Cloudflare (el MCP no expone plan,
  zonas ni Containers).
- **Memoria real (RSS) de Odoo** con los 8 módulos y **CPU por petición**: r3-odoo-medicion no había
  publicado cifras; mis cuentas usan CPU supuesta 3/10/25 % y el tamaño de cada tipo.
- **Tamaño de la imagen Docker** (limita basic a ≤ 4 GB) y **tiempo de arranque de Odoo** en Containers.
- Si un **Container** puede usar **Hyperdrive** (no hallé documentación).
- Página renderizada de **D1 Time Travel/limits**, **formatos de toMarkdown** y **Workers Builds**: leídas del
  repo oficial de docs, no de la web (bloqueada).
- **Tunnel gratis / Access gratis hasta 50 usuarios**: solo fuentes de terceros.
- **Smart Tiered Cache** por plan y reglas de caché del plan Free: no consultado a fondo.
- Si `toMarkdown` extrae **imágenes incrustadas en celdas** de Excel: no dice; probar (r3-brian-documentos).
- Precio de **PlanetScale** facturado por Cloudflare: fuera de alcance (r3-datos).
- Precio de almacenamiento de **snapshots** de Containers: no aparece en las páginas consultadas.
- Las «a demanda» son modelos con supuestos de uso inventados por mí (4 ráfagas de personal, 10 despertares
  web/día): reemplazar con datos reales de uso cuando existan.
