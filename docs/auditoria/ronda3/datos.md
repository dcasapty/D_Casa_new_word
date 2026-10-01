# r3-datos (ronda 3): ¿dónde vive PostgreSQL al menor costo sin arriesgar datos contables?

Agente: `r3-datos`. Fecha: 2026-10-01. Informe INCREMENTAL (se completa a medida que avanzan las mediciones).
Prototipo reproducible: `docs/auditoria/ronda3/datos/` (scripts + salidas resumidas). Datos y binarios en `/tmp/r3_datos/` (fuera de git).

## 0. Estado
- [ ] (A) Prototipo PG + WAL a S3 local: RPO, RTO, bytes, operaciones, costo R2
- [ ] (A') Apagado ordenado vs periodo de gracia SIGTERM
- [ ] (B) Snapshots de Containers
- [ ] (C) FUSE a R2
- [ ] (D) PostgreSQL gestionado gratis/casi gratis
- [ ] (E) Hyperdrive
- [ ] (F) Plan B: PC de tienda / VPS + Tunnel
- [ ] Recomendación

## 1. Fuentes oficiales usadas (Cloudflare, vía MCP `search_cloudflare_documentation`, consultadas 2026-10-01)

| Hecho | URL | Last updated |
|---|---|---|
| R2: $0,015/GB-mes; Clase A $4,50/M; Clase B $0,36/M; salida gratis; gratis 10 GB-mes, 1 M Clase A, 10 M Clase B; redondeo al siguiente millón / GB | https://developers.cloudflare.com/r2/pricing/ | 2026-08-07 |
| SIGTERM → espera hasta 15 min → SIGKILL (al parar, en *rollouts* y antes de que un host saque trabajo); reinicios de host «con cadencia irregular», sin duración garantizada | https://developers.cloudflare.com/containers/faq/ , /containers/concepts/architecture/ , /containers/configuration/rollouts/ | (páginas vigentes; rollouts: tras el SIGTERM, `onStop` corre «once the container process has exited») |
| Con la API de DO-Container (la de la política `durable_object`): al vencer el *inactivity timeout* «every process … receives SIGTERM, and Cloudflare stops the instance **shortly after, whether or not the processes exit**»; `destroy()` = sin tiempo de limpieza; Cloudflare **no despierta** al DO cuando la instancia para; *inactivity timeout* máx. 6 h y **no sobrevive a un reinicio del DO** | https://developers.cloudflare.com/sandbox/concepts/lifetime/ , /containers/api/durable-object-container/ | (vigentes) |
| Política `durable_object` (beta): rechaza `image`, `instance_type`, `max_instances`, rollouts y `constraints`; no se puede cambiar en una app existente (hay que crear otra app y otra clase DO); las instancias **no participan en rollouts** | /workers/wrangler/configuration/ , /containers/configuration/scheduling-policy/ , /containers/guides/migrate-to-durable-object-scheduling-policy/ , changelog 2026-09-30 | 2026-09-30 |
| Snapshots: solo política `durable_object`; FS raíz escribible; ni memoria, ni procesos, ni montajes; máx. 20 GB; TTL 30 días renovado al restaurar, no configurable; atados a la imagen; no hay API para listarlos | /containers/guides/snapshots/ , /containers/platform/limits/ , /containers/api/durable-object-container/ | 2026-09-30 |
| Unicidad global del DO: «possible that the Durable Object may no longer be current, and some other instance of the same Durable Object ID will have been created elsewhere» (partición de red o actualización) | https://developers.cloudflare.com/durable-objects/platform/known-issues/ | (vigente) |
| FUSE a R2: «Object storage is not a POSIX-compatible filesystem, nor is it local storage … should not expect native SSD-like performance» | https://developers.cloudflare.com/containers/examples/r2-fuse-mount/ | 2026-08-28 |
| Hyperdrive: se consume desde Workers (binding); solo modo transacción; sin `LISTEN/NOTIFY` (ver entrada de r3-cf-plataforma); PlanetScale Postgres facturado en la factura de Cloudflare al precio de PlanetScale | /hyperdrive/platform/pricing/ , /hyperdrive/planetscale/ , changelog 2026-06-18 | (vigentes) |
| Containers → bindings: solo por *outbound handlers* **HTTP/HTTPS (puertos 80/443)**; «Traffic on ports other than 80 and 443 is never routed through outbound» | /containers/configuration/outbound-traffic/ , /containers/configuration/workers-connections/ | 2026-09-30 |

## 5. (D) PostgreSQL gestionado gratis o casi gratis (Neon descartado por el dueño)

Patrón de Odoo que hay que tolerar: proceso siempre conectado (bus con `LISTEN/NOTIFY` en una conexión de sesión, hilo de cron que despierta cada minuto, `db_maxconn = 16` en `docker/entrypoint.sh:45`), así que **no hay inactividad real** (el «scale to zero» no ahorra nada) y **un pooler en modo transacción no sirve**. Tamaño medido de la base de prueba (`dcasa_test`, 8 módulos, catálogo con fotos, 0 transacciones): **211 MB** en PostgreSQL, de los cuales `ir_attachment` ocupa **120 MB** (71 MB son *assets* compilados de `ir.ui.view`, 77 MB imágenes sin comprimir; TOAST las deja en 120 MB) ⇒ **91 MB sin adjuntos**. Con las fotos fuera (OCA `fs_attachment` **19.0.1.1.3.4**, publicado en PyPI el 2026-09-26, «Development Status :: 4 - Beta», AGPL-3, depende de `fs_storage` 19.0.1.1.3.5 LGPL y `fsspec`; existe también `fs_attachment_s3` 19.0.1.2.1.4) la base arranca en ~90-100 MB. Fuente: `https://pypi.org/pypi/odoo-addon-fs-attachment/json` (consultada 2026-10-01).

| Proveedor (plan) | Precio | Límites relevantes | ¿Tolera Odoo? | Respaldo / PITR | Veredicto para contabilidad |
|---|---|---|---|---|---|
| **PlanetScale Postgres PS-5 single node** (se puede facturar en la factura de Cloudflare: oficial, `developers.cloudflare.com/hyperdrive/planetscale/`) | **$5/mes** [terceros; planetscale.com bloqueado: NO VERIFICADO en fuente primaria] | 1/16 vCPU, 512 MiB; `max_connections` 25 por defecto en PS-5; conexión directa al primario en 5432 con sesión completa (`LISTEN/NOTIFY` sí), PgBouncer aparte [terceros] | **Probablemente sí** (25 conexiones ≥ 16 de Odoo + cron + bus; bajar `db_maxconn` a 12). Riesgo: 1/16 vCPU para `-u` de módulos y para el arranque de Odoo (sin medir) | Respaldos cada 12 h, retención 2 días, **PITR dentro de la ventana** (hasta 5 min antes de ahora), almacenamiento de respaldos 2× disco incluido [terceros] | **Candidato más barato gestionado con PITR**. Un nodo (sin réplica). Exige la red de seguridad propia (pg_dump diario a R2) porque la retención es de solo 2 días. Medir latencia Container↔PlanetScale |
| Crunchy Bridge Hobby-0 | $9/mes | 2 núcleos, 512 MB; almacenamiento $0,10/GB; «Hobby tier … not intended for production usage», sin SLA [terceros; docs.crunchybridge.com y crunchydata.com bloqueados] | Probablemente sí | Incluye respaldos y PITR [terceros] | Alternativa; ojo: Crunchy es de Snowflake desde 2025 (Snowflake Postgres GA 2026-02-24); el propio proveedor dice «no producción» |
| Supabase Free | $0 | 500 MB; se pausa tras 7 días de inactividad; conexión directa **solo IPv6** (IPv4 = add-on $4 o pooler de sesión Supavisor, que sí admite `LISTEN/NOTIFY`) [terceros + supabase.com/docs vía buscador] | Cabe hoy (≈ 211 MB) | **Sin respaldos descargables ni PITR** en Free | **No** para contabilidad (sin respaldo del proveedor) |
| Supabase Pro | $25 + PITR desde $100 | — | Sí | PITR caro | No (precio) |
| Aiven Free | $0 | 1 CPU, 1 GB RAM, **1 GB disco, `max_connections` 20**, sin pooling; Aiven «se reserva» apagar servicios gratis sin actividad continua y **cambiar proveedor, región o configuración en cualquier momento** (repo oficial `aiven/aiven-docs`, `static/includes/free-tier-disclaimer.md`, commit 2026-09-30) | Justo (20 conexiones) | La página del plan gratis dice «Backups», pero la tabla de retención solo lista Hobbyist «None» / Startup 2 días: **retención del Free sin documentar** | **No** (puede cambiar región/configuración sin aviso) |
| Prisma Postgres Free | $0 | 500 MB, **200 000 operaciones/mes** (changelog 2026-08-28, terceros) | **No**: Odoo hace más de 200 k consultas al mes solo con el cron | — | No |
| Nile Free | $0 | 1 GB, 50 M «query tokens»; Pro $15 [terceros] | Orientado a multi-inquilino; no probado con Odoo | NO VERIFICADO | No recomendado |
| Koyeb Free | $0 | 0,25 vCPU, 1 GB RAM, 1 GB, **5 h de cómputo al mes**, duerme a los 5 min [terceros] | **No** (5 h/mes) | — | No |
| Xata | sin plan gratis; $0,012/h + $0,28/GB (≈ $8,8/mes) [terceros] | — | Posible | NO VERIFICADO | Más caro que PS-5 |
| Tembo Cloud | **cerrado** (creación deshabilitada 2025-05-05; migración final 2025-06-27) [HN / Neon guía] | — | — | — | Descartado |
| Render Postgres | Free **vence a los 30 días**; Basic-256mb $6-7; Basic-1gb $19-20 [terceros] | 256 MB RAM | Justo | Respaldos en pago | Peor que PS-5 |
| Railway | Hobby $5 con $5 de uso; RAM $10/GB-mes, CPU $20/vCPU-mes [terceros] | — | Sí | — | > $5 reales para PG 24/7 |
| Fly.io Managed Postgres Basic | $38/mes + $0,28/GB [terceros] | — | Sí | Sí | Caro |
| Oracle Cloud Always Free | $0 | A1 recortado a **2 OCPU / 12 GB** (desde 2026-06-15; aplicación desde 2026-08-18); reclama VMs ociosas (p95 CPU y red < 20 % en 7 días) [InfoQ 2026-07, linuxiac] | Recursos sobran | Lo montas tú | **No** (puede reclamar o terminar la VM; ya cambió reglas sin avisar) |
| AWS Free | crédito $100 + $100, plan de **6 meses** (desde 2025-07); Aurora PG en Free Tier desde 2026-03 [aws.amazon.com/about-aws/whats-new] | — | Sí | Sí | Solo 6 meses: no es una base para años |
| Azure (cuenta gratis) | Flexible Server B1MS 750 h + 32 GB + 32 GB de respaldo **12 meses** [learn.microsoft.com vía buscador] | — | Sí | Sí | Solo 12 meses |
| GCP Always Free | VM e2-micro (1 GB RAM) + 30 GB de disco en us-west1/us-central1/us-east1; **solo 1 GB/mes de salida** [terceros + cloud.google.com/free vía buscador] | PG propio en la VM | Sí (PG pequeño) | Lo montas tú (WAL a R2) | Gratis pero: la salida Odoo↔BD se factura por encima de 1 GB y es una VM que se opera igual que un VPS |

Conclusión (D): **no existe un PostgreSQL gestionado gratuito apto para contabilidad** (los gratis no dan respaldo del proveedor, cambian reglas o limitan horas/operaciones). El escalón «casi gratis» con PITR real es **PlanetScale PS-5 a $5/mes** (incluso pagable en la factura de Cloudflare), seguido de Crunchy Hobby-0 a $9. Ambos son de un solo nodo y con retención corta: se combinan con el `pg_dump` diario propio a R2.

## 6. (E) Hyperdrive

- Hyperdrive es un *pool* y caché que se consume **desde un Worker** mediante *binding*; no expone un puerto PostgreSQL al que un proceso Python (psycopg2) pueda conectarse. Los Containers solo alcanzan *bindings* por *outbound handlers* **HTTP/HTTPS en 80/443** («Traffic on ports other than 80 and 443 is never routed through outbound»: https://developers.cloudflare.com/containers/configuration/outbound-traffic/ , Last updated 2026-09-30). ⇒ **Odoo dentro de un Container no puede usar Hyperdrive** (tendría que hablar el protocolo de PostgreSQL por HTTP, cosa que psycopg2 no hace).
- Aunque pudiera: solo modo transacción, sin `LISTEN/NOTIFY` ni *advisory locks* (entrada de r3-cf-plataforma, `/hyperdrive/reference/supported-databases-and-features/`): rompe el bus de Odoo.
- **Dónde sí sirve**: para los componentes del borde (Brian en Workers, sitio estático, socios) que lean la misma base PostgreSQL (p. ej. PlanetScale) con consultas cortas; costo $0 adicional en Workers Paid (consultas ilimitadas: https://developers.cloudflare.com/hyperdrive/platform/pricing/).

## 3. (B) Snapshots de Containers con PostgreSQL

Hechos oficiales (tabla §1): solo con la política `durable_object` (beta desde 2026-09-30, no convertible: hay que crear otra app y otra clase DO); capturan el FS raíz escribible, **no** memoria ni procesos ni montajes; máx. 20 GB; TTL 30 días renovado al restaurar; **atados a la imagen**; inmutables; sin API para listarlos (hay que guardar el `id` en el storage del DO).

Consecuencias para PostgreSQL:
1. **Consistencia**: un snapshot tomado con PostgreSQL corriendo es, como mucho, una «copia de un disco que se apagó de golpe» (la doc no dice que sea atómico en el instante; NO VERIFICADO). PostgreSQL sabe recuperarse de un corte si la copia es atómica a nivel de sistema de archivos (*crash-consistent*); si no lo es, puede quedar corrupta sin aviso. Uso seguro: `pg_backup_start()` → snapshot → `pg_backup_stop()` (y guardar el `backup_label`), o parar PostgreSQL (`pg_ctl stop -m fast`) antes del snapshot. Con `--data-checksums` (lo usa el prototipo) al menos se detecta la corrupción.
2. **No sustituye al WAL**: todo lo escrito después del último snapshot se pierde si el host cae (SIGKILL sin gracia). El snapshot solo acelera el arranque.
3. **Atado a la imagen**: cada despliegue de una imagen nueva invalida el arranque rápido; el primer arranque tras el deploy vuelve a restaurar desde R2 (pgBackRest) y crea un snapshot nuevo.
4. **Combinación correcta**: *snapshot = arranque rápido; WAL en R2 = durabilidad*. Flujo: al arrancar, si hay snapshot de la misma imagen → `start({containerSnapshot})`, PostgreSQL arranca desde ese estado y luego aplica el WAL archivado posterior (configurado como restauración *standby* con `restore_command = pgbackrest archive-get` hasta el final del archivo, y promoción). Si no hay snapshot válido → restauración completa con pgBackRest. Tras el arranque, snapshot nuevo con PostgreSQL en modo respaldo. Para una base de ~100-200 MB el ahorro es pequeño: la restauración completa medida en local ya es de decenas de segundos (§2); **el snapshot no compensa su complejidad aquí**.
5. Beta pública de un día de antigüedad (2026-09-30): no apoyar datos contables en ella.

## 7. (F) Plan B: PostgreSQL en una PC de la tienda o en un VPS barato, con Cloudflare Tunnel

- **VPS** (cifras de `ronda2/cf-costos.md` §4.4, de terceros y del 2026-09-30): Hetzner CX23 €5,49 / CX33 €8,49 (+20 % de copias de imagen), solo UE; Contabo ~€4,50-5,36; DigitalOcean/Vultr 2 vCPU/4 GB $20-24 en EE. UU. Con Odoo **y** PostgreSQL en el mismo VPS (sin Container) la latencia Odoo↔BD es ~0 y las sesiones persisten. Tunnel y Access son gratis. Es lo que la ronda 2 recomendó; esta ronda lo confirma como la opción con mejor relación costo/riesgo si el dueño acepta operar un servidor.
- **Odoo en Container + PostgreSQL en VPS por Tunnel**: un Container no puede abrir TCP a un origen privado del túnel salvo por internet público (el *outbound handler* solo es HTTP; NO VERIFICADO un camino TCP privado Container→Tunnel). Exponer 5432 del VPS a internet con TLS y lista de IP no es posible porque los Containers no tienen IP de salida fija (NO VERIFICADO). Además paga dos plataformas: **descartado** (igual que la opción C de la ronda 2).
- **PC de la tienda** (Odoo + PostgreSQL en una PC de La Chorrera, publicada con Tunnel): costo de hosting $0, pero (a) cortes de luz e internet de la tienda = sitio caído y riesgo de apagado sin gracia (mitigar con UPS y `synchronous_commit=on`, `fsync=on`, `full_page_writes=on`, disco SSD con protección ante cortes), (b) robo o daño del equipo = la base se va con él (mitigado solo por WAL + pg_dump en R2), (c) subida residencial limita el sitio. Apta como **servidor de oficina** o de contingencia, no como tienda en línea 24/7. Si el dueño la elige: misma receta de respaldo que el prototipo (pgBackRest → R2 cada 60 s + `pg_dump` diario + prueba de restauración).

## 4. (C) FUSE a R2 como directorio de datos de PostgreSQL: NO

Razones con fuente:
1. **Cloudflare lo dice**: «Object storage is not a POSIX-compatible filesystem, nor is it local storage» (https://developers.cloudflare.com/containers/examples/r2-fuse-mount/, Last updated 2026-08-28). El ejemplo oficial usa tigrisfs; su README no documenta semántica de `fsync` (leído en GitHub `tigrisdata/tigrisfs`, 2026-10-01).
2. **PostgreSQL exige un FS que se comporte como disco local**: la doc de PostgreSQL 16 (`doc/src/sgml/runtime.sgml`, rama `REL_16_STABLE` del repo `postgres/postgres`; postgresql.org bloqueado por el proxy) dice que con NFS «PostgreSQL does nothing special … assumes NFS behaves exactly like locally-connected drives» y que si un `fsync` del cliente no llega a almacenamiento permanente «could cause corruption similar to running with the parameter fsync off».
3. **s3fs (otro adaptador citado por Cloudflare) documenta**: «random writes or appends to files require rewriting the entire object», «no atomic renames of files or directories», «no coordination between multiple clients mounting the same bucket» (README de `s3fs-fuse/s3fs-fuse`, rama master, 2026-10-01). PostgreSQL escribe páginas de 8 KB al azar dentro de archivos de 1 GB y depende de `rename()` atómico (p. ej. `pg_control`, archivos de estado del WAL): cada página escrita reescribe el objeto entero, y un corte a mitad deja estado sin garantía.
4. Medición propia: ver §4.1 (prototipo `05_fuse.sh`).

## 8. (A) Diseño «PostgreSQL dentro del Container + WAL a R2», si se elige pese a todo

Piezas (todas probadas en el prototipo salvo las marcadas):
1. **Imagen**: añadir `postgresql-16` y `pgbackrest` (Ubuntu 24.04 trae pgBackRest 2.50, el probado) al `docker/Dockerfile`; `tini` ya es PID 1 (`docker/Dockerfile:61`), así que el SIGTERM llega al entrypoint.
2. **`docker/entrypoint.sh`** (hoy solo genera `odoo.conf` y migra): nuevo bloque previo:
   - `pgbackrest.conf` desde secretos (`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `PGBR_CIPHER_PASS`), `repo1-s3-endpoint=<cuenta>.r2.cloudflarestorage.com`, `repo1-s3-region=auto`, `repo1-s3-uri-style=path`, cifrado `aes-256-cbc`, `compress-type=zst`, `repo1-bundle=y`.
   - **Candado de instancia única** (NO probado): antes de restaurar, escribir en R2 un objeto `lease` con `If-Match` del ETag anterior (R2 admite PUT condicional: https://developers.cloudflare.com/r2/api/s3/extensions/) con el número de generación que pasa el DO; el `archive_command` envuelto comprueba la generación y aborta si otra instancia la superó. pgBackRest además rechaza un segmento que ya existe con otro contenido (red de seguridad, no candado).
   - `pgbackrest restore` (o `initdb` + `stanza-create` si el repositorio está vacío **y** el DO dice «base nueva»: nunca decidir «nueva» solo porque falló la conexión, cf. infra I-06), arrancar PostgreSQL, esperar `pg_is_in_recovery() = f`, **`CHECKPOINT`** (hallazgo §2.3) y lanzar el vigilante `pg_switch_wal()` cada 60 s.
   - `trap` de SIGTERM: parar Odoo → `CHECKPOINT` → `pg_switch_wal()` → esperar `pg_stat_archiver.last_archived_wal` → `pg_ctl stop -m fast` (§2.4) → salir.
   - Respaldo base: semanal (y tras cada restauración, para acortar el replay), lanzado por el cron del Worker vía una ruta interna o por `pg_cron`/hilo propio. NO VERIFICADO en Container.
   - `DB_HOST=127.0.0.1`, `db_sslmode=disable`; quitar `CREATE EXTENSION` por `sql()` que traga errores.
3. **`edge/`**: migrar a `scheduling_policy: "durable_object"` exige **app y clase DO nuevas** (no convertible; oficial) y reescribir `OdooContainer` sobre `ctx.container.start({image, instance})`; `max_instances` desaparece (la unicidad la da el ID del DO, con la salvedad oficial de que en partición/actualización puede existir otra instancia: de ahí el candado en R2). Mantener `setInactivityTimeout` alto, recordando que no sobrevive a un reinicio del DO (oficial). Sin snapshots al principio (§3).
4. **Respaldo independiente**: `pg_dump -Fc` diario cifrado a otro prefijo/bucket de R2 + restauración de prueba automática (§9).

Modos de fallo: (a) host apagado sin gracia u OOM (sin swap: OOM ⇒ reinicio) → se pierde lo no archivado (RPO medido ≤ 60 s en régimen, hasta 5 min sin la mitigación); (b) dos instancias (partición/actualización del DO) → dos líneas de tiempo escribiendo al mismo repositorio = *split-brain* contable; solo el candado lo evita; (c) actualización de imagen → SIGTERM y apagado ordenado (medido §2.4), luego restauración completa; (d) R2 caído al arrancar → la tienda no arranca (RTO = lo que dure R2); (e) corrupción silenciosa → `--data-checksums` + `pgbackrest verify` + restauración de prueba diaria; (f) disco del Container (8-12 GB) lleno por WAL si R2 no responde → PostgreSQL se detiene: alerta sobre `failed_count`.

## 2. (A) Prototipo medido: PostgreSQL efímero + archivado continuo de WAL a S3 + restauración

### 2.1 Montaje (reproducible)
- `docs/auditoria/ronda3/datos/env.sh` (variables), `01_s3_local.sh` (S3 local: **moto 5.x detrás de stunnel** en 9100/9101, porque MinIO (`dl.min.io`) está bloqueado por el proxy y el TLS de werkzeug corta sin `close_notify`, que pgBackRest/OpenSSL 3 rechaza), `02_cluster.sh` (PostgreSQL 16 en 5440, `initdb --data-checksums`, `archive_mode=on`, `archive_timeout=60`, `wal_recycle=off` + `wal_init_zero=on`; restaura el `pg_dump` de `dcasa_test`; `stanza-create`; respaldo base completo), `carga.py` (simula asientos: 1 INSERT+COMMIT/s con filas deterministas y registro de cada COMMIT confirmado), `verificar.sql` (conteos, huecos, filas corruptas, md5 por tabla), `03_ensayo_muerte.sh` (carga N s → `kill -9` del postmaster y todos sus hijos, incluido el archivador → `rm -rf` del directorio de datos → `pgbackrest restore` → arranque → espera promoción → verificación), `04_apagado.sh` (apagado ordenado vs ingenuo), `06_reposo.sh` (peticiones S3 y bytes por hora), `s3_inventario.py`, `costo_r2.py`, `05_fuse.sh` (§4.1).
- pgBackRest **2.50** (paquete de Ubuntu 24.04), repositorio cifrado `aes-256-cbc`, `compress-type=zst` nivel 3, `process-max=2`.
- Base: `pg_dump -Fc` de `dcasa_test` = 114 MB (18 s); `pg_restore -j2` = 23 s; en el clúster 191,8 MB; **respaldo base pgBackRest: 102,8 MB en el repositorio, 4 546 archivos, 98 s** (moto es lento por objeto: 1 PUT por archivo).

### 2.2 Muerte del contenedor sin gracia (kill -9 + disco borrado): 12 ensayos
Tabla completa en `salidas/resumen_muerte.txt` (salida por ensayo en `salidas/muerte-*.txt`).

| Ensayos | RPO (s) | RTO total (s) | Integridad |
|---|---|---|---|
| 1-2 (primer arranque y primera restauración, sin mitigación) | 28,1 · 44,2 | 48,2 · 50,7 | 0 corruptas, md5 iguales |
| 3-5 (tras restauración, sin mitigación) | **169 · 125 · 200 (toda la carga)** | 57,6 · 65,1 · 64,3 | 0 corruptas, md5 iguales; se perdió todo lo posterior a la restauración |
| 7-12 (con `CHECKPOINT` tras promover; carga 95-200 s) | **38,1 · 52,2 · 8,1 · 23,0 · 33,1** (mediana **33 s**, máx. 52 s) | 42,1 · 44,1 · 44,6 · 44,7 · 50,6 | 0 corruptas, md5 iguales |

- RPO = segundos entre el último COMMIT confirmado al cliente y el último COMMIT restaurado. En régimen está acotado por `archive_timeout` (60 s) + subida.
- RTO = desde directorio vacío hasta PostgreSQL promovido y aceptando escrituras; **mediana 46 s en 12 ensayos** (pgBackRest 38-62 s; replay+promoción 2-7 s). Es optimista: S3 en la misma máquina. Con R2 real se suma la red (≈ 103 MB y ~4 500 GET sin `repo1-bundle`). Arrancar Odoo después: 3,0-3,7 s (r3-odoo-medicion).
- El campo `asientos_huecos = 99826` de los ensayos 6-12 es una fila de diagnóstico manual (id 100000), no un hueco real: los ids posteriores son contiguos.

### 2.3 HALLAZGO: tras cada restauración el archivado queda mudo hasta `checkpoint_timeout`
En 4 de 6 promociones (líneas de tiempo 3, 4, 5 y 7) PostgreSQL 16 **no forzó el cambio de segmento a los 60 s** pese a la carga continua: el primer `pushed WAL file` apareció justo con `checkpoint starting: time`, 5 min después del `end-of-recovery checkpoint` (reproducido a mano en TL7: promoción 00:38:50, primer push 00:43:50, `pg_stat_archiver.archived_count` congelado en 1). En TL2 y TL6 sí archivó a los 60 s; el patrón observado es que la carga empezó 1-3 s después de promover (en TL2/TL6, 9-12 s). Causa exacta en el código de PostgreSQL: no verificada (hipótesis: el checkpointer calcula su espera mientras aún se considera «en recuperación» y duerme `checkpoint_timeout`). **Mitigación medida**: un `CHECKPOINT` explícito tras la promoción (5/5 ensayos archivaron a los 60 s). Defensa adicional recomendada: vigilante que llame `pg_switch_wal()` cada 60 s si el LSN avanzó, y alerta si `last_archived_time` > 2 min.

