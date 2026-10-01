# Auditoría de infraestructura (`infra`)

Alcance: `docker/`, `docker-compose.yml`, `Makefile`, `.github/workflows/`, `edge/`, `scripts/`,
`pyproject.toml`. Auditoría estática (vendor/odoo no está en este entorno; no se ejecutó nada).
Fecha: 2026-09-30.

**Regla de este informe sobre Cloudflare/Neon:** no tengo acceso a los precios ni límites vigentes.
Todo número de precio, límite o comportamiento de Cloudflare/Neon lleva **(por verificar con el MCP de
Cloudflare / la consola de Neon)**. Las cuentas de abajo sirven para el orden de magnitud y para
decidir; hay que rehacerlas con los valores reales antes de comprometer presupuesto.

## 1. Resumen ejecutivo

La base técnica está **bien pensada y más madura que lo habitual para un proyecto sin producción**:
imagen multi-etapa y sin root, configuración sin secretos en la imagen, Worker con lógica testeable,
CI con concurrencia, permisos mínimos y despliegue condicionado a que pase todo. El diseño es coherente
con su propia documentación.

Los riesgos reales no están en el código sino en **tres decisiones de operación**:

1. **El presupuesto previsto ($5/mes + $1 + R2) no alcanza para Odoo en Containers.** El plan de $5 es la
   cuota base del Worker; el contenedor se factura aparte por uso (memoria aprovisionada mientras
   corre). Con la configuración actual (`standard-2`, cron cada 10 min que impide dormir) el contenedor
   queda encendido 24/7: orden de **$45/mes solo de contenedor**, más Neon (~$0–20). Total realista
   **$35–70/mes**, no $6. Ver §4. Es la decisión que el dueño debe tomar antes de migrar.
2. **Las actualizaciones de esquema ocurren dentro del arranque del contenedor**, en cada push a `main`
   (incluso si solo cambió un `.md`), sin candado, sin copia previa y sin camino de retorno. Es seguro
   con una sola instancia sin despliegues solapados; es frágil en cuanto algo falla o se escala.
3. **No hay respaldo independiente del proveedor de la base** (la copia a R2 está solo en el plan) y la
   pimienta del PIN de socios vive únicamente dentro de Cloudflare sin copia.

Veredicto de viabilidad: **Odoo 19 en Cloudflare Containers + Neon es viable** para este volumen
(una tienda, pocos usuarios internos), con dos condiciones: medir la latencia contenedor↔Neon antes de
decidir (§3, I-05) y mover las migraciones fuera del arranque (I-02). Si el presupuesto real es ≤ ~$10/mes,
la alternativa ya prevista en el repo (VPS + `cloudflared`) es la opción honesta (§4.4).

## 2. Hallazgos priorizados

Severidad según la bitácora. `ruta:línea` verificado leyendo el archivo.

### ALTO

**I-01 · El costo real no cabe en el presupuesto; y el cron de 10 min anula `sleepAfter`.**
- `edge/wrangler.jsonc:14` (`standard-2`, 1 vCPU/6 GiB *(por verificar)*), `edge/src/index.ts:50`
  (`sleepAfter = "30m"`) y `edge/src/index.ts:97-99` + `edge/wrangler.jsonc:24` (cron `*/10` que hace
  `fetch /web/health`): cada 10 min se renueva la actividad, el contenedor **nunca duerme**. El comentario
  del cron lo dice; lo que falta es el costo: memoria aprovisionada 6 GiB × 720 h.
- `docs/ARQUITECTURA.md` ("El contenedor duerme tras 30 min sin tráfico") describe un comportamiento que
  con el cron activo no ocurre; la doc y el código se contradicen.
- Arreglo: decidir explícitamente entre (a) 24/7 en `standard-1` (4 GiB) y medir si alcanza, (b) dormir de
  noche (cron solo en horario laboral con `0,10,20,30,40,50 12-23 * * 1-6` UTC; Panamá es UTC-5) aceptando
  cold start y crons nocturnos detenidos, o (c) VPS. Corregir `ARQUITECTURA.md`.

**I-02 · Migraciones y actualización de módulos en el arranque: sin candado, sin copia, sin rollback.**
- `docker/entrypoint.sh:77-85`: si `dcasa.deployed_version` != `APP_VERSION` corre `odoo -i … -u …` *antes*
  de abrir el puerto, en cada deploy (`APP_VERSION` = SHA, `.github/workflows/ci.yml:191`), incluso si el
  commit solo toca `docs/`. Consecuencias:
  1. Cada push a `main` = reinicio + actualización de 8 módulos = minutos de sitio caído/lento
     (Cloudflare reemplaza la instancia; Odoo no atiende hasta terminar el `-u`). El `-u` de
     `website_dcasa`/`dcasa_catalogo` (323 fotos, 31 MB de assets) no es trivial.
  2. **Sin exclusión mutua**: dos contenedores arrancando a la vez (solape de un rolling deploy, o el
     día que `max_instances` > 1) ejecutan `-u` en paralelo sobre la misma base. Odoo no lo protege
     (se verá como bloqueos/`deadlock detected`, datos de XML duplicados o módulo a medio actualizar).
     Hoy `max_instances: 1` (`wrangler.jsonc:15`) lo mitiga, **no lo elimina** (por verificar cómo
     solapa Containers dos versiones durante un deploy).
  3. **Sin rollback real**: volver a un SHA anterior lanza `-u` con código viejo sobre un esquema ya
     migrado hacia adelante (`entrypoint.sh:78` compara por igualdad, no por orden). Odoo no tiene
     downgrade. El único retorno es restaurar la base (PITR/rama de Neon) y no hay paso que lo prepare.
  4. Si `-u` falla, `set -e` (`entrypoint.sh:11`) termina el contenedor: bucle de reinicios y sitio caído
     hasta nuevo push, sin aviso.
- Arreglo: (i) paso de CI **previo** al `wrangler deploy`: crear rama/snapshot de Neon, correr
  `docker run … -u … --stop-after-init` contra la base (un solo proceso, en un job con `concurrency`),
  y solo si sale bien desplegar; (ii) el contenedor solo compara versión y, si difiere, **no migra**
  (`ODOO_AUTO_UPDATE=0` por defecto en producción; dejar el `-u` para base nueva y desarrollo);
  (iii) si se quiere conservar la migración en el arranque, protegerla con `pg_advisory_lock` mantenido
  por una sesión `psql` durante todo el `-u`; (iv) desplegar solo cuando cambien `addons/`, `docker/`,
  `edge/`, `vendor/` (filtro `paths:`), no por docs.

**I-03 · No existe respaldo independiente de la base (y nunca se ha probado una restauración).**
- `docs/PLAN.md` Fase 3 ("PITR de Neon + copia diaria a R2") sigue sin marcar; no hay script ni workflow de
  respaldo (`scripts/` no lo tiene; `.github/workflows/` tampoco). `docs/DESPLIEGUE.md` ("Operación →
  Respaldos") menciona `pg_dump` manual.
- PITR de Neon vive en el mismo proveedor/cuenta: un borrado del proyecto, una cuenta comprometida o un
  límite de retención corto (el plan gratuito retiene poco: *por verificar*) se llevan datos y respaldo.
  Como **los adjuntos viven en la base** (`dcasa_base/__init__.py:157-158`), un `pg_dump` completo es
  además el respaldo de imágenes y PDF: es una virtud (un solo artefacto a proteger).
- Arreglo: workflow programado (diario) `pg_dump -Fc` desde Actions → cifrar (`age`) → R2 con ciclo de
  vida (p. ej. 7 diarios + 4 semanales + 12 mensuales) y una alarma si el workflow falla; **ensayo de
  restauración** trimestral a una rama de Neon y arranque de Odoo contra ella. Documentar RPO/RTO
  (objetivo razonable: RPO ≤ 24 h con PITR adicional, RTO ≤ 2 h).

**I-05 · Latencia contenedor → Neon sin medir (por verificar).**
- Odoo ejecuta decenas a cientos de consultas por página y **cada una es un viaje de red** a Neon
  (`entrypoint.sh:35`, `DB_HOST` de Neon en `us-east`). El contenedor no tiene región elegible explícita
  (`getContainer(env.ODOO, "odoo-main")`, `edge/src/index.ts:80`): se ubica cerca de donde el Durable
  Object se crea por primera vez (*por verificar* si `locationHint` de DO fuerza Containers a
  `enam`). Un contenedor en otra región que Neon multiplica el tiempo de cada página por el RTT.
- Arreglo: antes de migrar, desplegar en un entorno de prueba y medir RTT (`pg_isready`/`SELECT 1` ×100)
  y TTFB de `/`, `/shop`, `/web/login`. Crear la DO con `locationHint: "enam"` y la base de Neon en
  `aws-us-east-1/2` según la medición. Si el RTT > ~20 ms de forma sostenida, reconsiderar (VPS con
  PostgreSQL local, sección 4.4).

### MEDIO

**I-04 · Sesiones en disco efímero: se pierden carritos y logins con cada reposo/deploy/reinicio.**
- Odoo guarda sesiones en `data_dir` (`entrypoint.sh:31` → `/var/lib/odoo/data`), no en la base. Documentado
  para el backend (`ARQUITECTURA.md`: "se cierran las sesiones"), pero **no** se menciona el efecto en la
  tienda: el carrito (`sale_order_id` en sesión) y el checkout en curso se pierden, y Cloudflare puede
  reiniciar contenedores por mantenimiento en cualquier momento (*por verificar*). Con un deploy por push
  (I-02) será frecuente.
- Arreglo: reducir deploys (I-02.iv); avisar en el runbook que no se despliega en horario de venta;
  evaluar (a) sincronizar `sessions/` a R2 al apagar y restaurar al iniciar (latencia y consistencia
  discutibles) o (b) un `session_store` propio en PostgreSQL (hay que escribirlo y probarlo; no es de
  Community). Mientras tanto, no escalar a más de una instancia: sin sesiones compartidas, dos réplicas
  rompen el login.

**I-06 · `sql()` se traga todos los errores y eso puede disparar la rama "base nueva" sobre una base viva.**
- `docker/entrypoint.sh:55-57`: `psql … 2>/dev/null || true`. Si Neon está despertando, hay un fallo de
  red/TLS o el usuario pierde permiso, `installed` queda vacío (`:62`) y `[[ "$installed" != "installed" ]]`
  (`:63`) ejecuta la instalación completa y luego **restablece la contraseña de `admin`** a
  `ADMIN_USER_PASSWORD` (`:67-72`), pisando la que el dueño haya cambiado. `-i` sobre módulos ya
  instalados es casi un no-op, pero el reseteo de clave y la escritura de versión son reales.
  Con `deployed=""` (`:77`) se fuerza además un `-u` innecesario.
- Arreglo: distinguir "consulta falló" de "resultado vacío": reintentar con espera (p. ej. 5 × 3 s) y
  abortar el arranque si no hay conexión; usar `to_regclass('ir_module_module')` para decidir "base
  nueva" solo si la tabla no existe; no tocar la clave de `admin` fuera de la primera instalación
  verificada.

**I-07 · Arranque en frío sin experiencia de error y "sano" ≠ "listo".**
- `edge/src/index.ts:52` (`pingEndpoint = "web/health"`) y `entrypoint.sh` (hasta ~3 `psql` + carga del
  registro de 8 módulos + Website): arranque en frío típico de decenas de segundos (el doc dice "~10 s";
  no medido) y de minutos si toca `-u`/instalación. Odoo abre el puerto **antes** de precargar el registro,
  así que `/web/health` puede responder OK mientras las primeras peticiones reales esperan (por verificar
  en Odoo 19). El Worker no captura el fallo de `forward` (`index.ts:80-84`, `handler.ts:33`): el visitante
  recibe un 500/1101 pelado; el tiempo de espera de puertos de `@cloudflare/containers` *(por verificar
  el valor por defecto)* puede ser menor que una instalación.
- Arreglo: envolver `forward` en `try/catch` y devolver 503 + `Retry-After: 30` con una página estática
  de "estamos despertando"; ajustar las opciones de espera al cold start medido; exponer una sonda de
  preparación que haga `?db_server_status=1` o consulte `/` (no solo `/web/health`).

**I-08 · El contenedor de CI/CD despliega una imagen distinta a la que probó.**
- `.github/workflows/ci.yml:116-126` construye y prueba `dcasa-odoo:ci` con caché GHA; el job `deploy`
  (`:147-195`) no la reutiliza: `wrangler deploy` (con `"image": "../docker/Dockerfile"`,
  `wrangler.jsonc:11`) **reconstruye desde cero en un runner frío** (apt + compilación de dependencias
  Python, varios minutos) y sube otra imagen. Lo probado y lo desplegado pueden diferir (paquetes apt sin
  fijar, tag de ubuntu que se mueve, versiones de pip).
- Arreglo: construir una sola vez, etiquetar con SHA, empujar al registro de Cloudflare
  (`wrangler containers push` / imagen por tag en `wrangler.jsonc`; *por verificar sintaxis vigente*) y
  desplegar esa referencia por digest. Además, que `deploy` tenga `paths:` (I-02.iv) y un `concurrency`
  propio `cancel-in-progress: false` (hoy lo hereda del grupo de CI; bien para `main`, a verificar).

**I-09 · `up media` (948 MB, 325 archivos) está versionado: `.git` pesa 1,4 GB.**
- `git ls-files "up media"` → 325; `du` → 948 MB. `.dockerignore:13` la excluye de la imagen (bien), pero
  **todos los jobs** hacen `actions/checkout` (`ci.yml:25,60,90,115,167`) y `fetch-depth: 1` igual baja
  todos los blobs del árbol actual; además, cada clon completo (Claude Code, nuevas máquinas) arrastra
  1,4 GB. Los originales no los necesita ningún test ni la imagen (la imagen usa `addons/dcasa_catalogo`).
- Arreglo: `sparse-checkout` para excluir `up media` en CI (ahorra minutos por job), y a mediano plazo
  sacarlas del historial (`git filter-repo`) y guardarlas en R2 (10 GB gratis *(por verificar)*) o LFS.
  Decisión con el dueño: reescribir historia cambia todos los SHA.

**I-10 · `-u` solo de los módulos propios: una actualización de Odoo no aplica a los módulos estándar.**
- `entrypoint.sh:82` y `docs/DESPLIEGUE.md` ("Actualizar Odoo… el contenedor actualiza los módulos solo").
  `-u dcasa_*` actualiza esos módulos y sus *dependientes*, **no** sus dependencias (`sale`, `account`,
  `website`…). Un parche de la 19.0 que cambie vistas/datos XML de módulos estándar no se carga en la
  base hasta un `-u all`. El código Python sí cambia (imagen nueva), así que puede haber desajuste
  código↔vistas en DB.
- Arreglo: guardar el commit de `vendor/odoo` (`ARG ODOO_COMMIT`, `git -C vendor/odoo rev-parse HEAD`)
  en el parámetro de versión y, si cambió, correr `-u all` en el paso de migración de CI (I-02),
  previa rama de Neon.

**I-11 · Variables con marcador (`CAMBIAR.neon.tech`) y secretos subidos después del deploy.**
- `edge/wrangler.jsonc:30` (`DB_HOST: "CAMBIAR.neon.tech"`) y `ci.yml:192-194` (solo pasa `--var` si la
  variable de GitHub no está vacía). Si `DB_HOST` de GitHub falta, se despliega con el marcador y el
  contenedor entra en bucle con error de DNS. El paso guarda (`ci.yml:157-165`) valida solo los secretos
  de Cloudflare.
- `ci.yml:196-204` sube `DB_PASSWORD`/`ADMIN_PASSWORD` *después* de `wrangler deploy` y sin validar vacío
  (`process.env.X` ausente → `""`/`undefined`). Un deploy manual (`wrangler deploy` a mano) sin
  `--var APP_VERSION` fija `APP_VERSION=dev` (`index.ts:62`) y fuerza un `-u`; uno sin `DB_HOST` pisa el
  valor de CI con el marcador.
- Arreglo: el guard falla (no omite) si `DB_HOST` contiene `CAMBIAR` o faltan `DB_USER/DB_NAME`;
  validar no vacíos los secretos obligatorios; usar `wrangler deploy --secrets-file`/`versions upload
  --secrets` si el MCP/CLI vigente lo permite (*por verificar*) para atómico secretos+código; quitar el
  marcador del JSON y exigir las variables.

**I-12 · Observabilidad y alertas inexistentes.**
- `edge/src/handler.ts:19` y `routing.ts:13`: `/__edge/health` responde "ok" desde el Worker **sin tocar
  Odoo ni la base**; sirve para el Worker, no para el sitio. `index.ts:98`: el `fetch` del cron va en
  `waitUntil` sin `try/catch` ni registro del resultado: si Odoo no levanta, nadie se entera.
- `wrangler.jsonc:6` (`observability: enabled`): logs del Worker, retención corta *(por verificar)*.
  `docs/DESPLIEGUE.md` afirma que "incluye los del contenedor": *por verificar* (¿stdout del contenedor
  llega a Workers Logs, con qué retención?). No hay alertas (errores 5xx, contenedor caído, cron de
  respaldo fallido, espacio de Neon), ni Sentry/equivalente para excepciones de Odoo.
- Arreglo: monitor externo (Cloudflare Health Checks/Notifications o UptimeRobot gratuito) contra
  `/web/health?db_server_status=1` y `/shop` cada 1–5 min con aviso a WhatsApp/correo; registrar el
  resultado del ping del cron (`console.log` estructurado con status y ms); alerta de tasa de errores del
  Worker; destino de logs persistente si el costo lo permite (R2/Logpush, *por verificar*); `log_level`
  ya es configurable (`entrypoint.sh:46`).

**I-13 · Secreto maestro = clave del usuario admin, y `/jsonrpc` con servicio `db` no está bloqueado en el borde.** (coordinar con `seguridad`)
- `entrypoint.sh:67`: `ADMIN_USER_PASSWORD` por defecto es `ADMIN_PASSWORD` (la contraseña maestra,
  `:38`). Quien conozca la del panel conoce la que permite volcar la base. `routing.ts:12`
  bloquea `/web/database`, `/xmlrpc/db`, `/xmlrpc/2/db` pero no `/jsonrpc` (servicio `db`); `list_db = False`
  (`:37`) oculta el listado, y `dump`/`restore` siguen pidiendo la maestra. Defensa en profundidad:
  clave maestra distinta y larga (DESPLIEGUE.md ya pide "larga y aleatoria") y `ADMIN_USER_PASSWORD` separado
  obligatorio en producción. (Por verificar en vendor/odoo 19 qué servicios `db` siguen vivos.)

**I-14 · Pimienta de PIN sin copia de respaldo.**
- `.github/workflows/ci.yml:224-234` la genera en el primer deploy y "nadie la ve"; `docs/DESPLIEGUE.md`:
  "jamás se rota". Un secreto de Worker es de solo escritura: si se borra el Worker, se cambia de cuenta
  (la migración a otra cuenta/entorno es justo lo que viene), o se restaura la base en staging, **todos los
  PIN dejan de funcionar** y no hay recuperación. Un volcado de la base solo no basta para reconstruir el
  servicio (DR).
- Arreglo: generarla fuera (una vez), guardarla en gestor de contraseñas del dueño **y** como secreto
  `DCASA_PIN_PEPPER` del environment; el workflow la sube si falta. Incluir en el runbook de DR.

**I-15 · Sin entorno de staging ni versionado explícito.**
- Un solo `environment: production` (`ci.yml:152`) y un solo Worker (`wrangler.jsonc:2`). No hay
  etiquetas/releases ni CHANGELOG; la versión desplegada es el SHA (`index.ts:62`).
- Arreglo barato: staging = **rama de Neon** (copia instantánea de producción, costo de almacenamiento
  incremental *(por verificar)*) + `env.staging` en `wrangler.jsonc` con `max_instances: 1`,
  `sleepAfter: "5m"`, sin cron y sin dominio propio; se levanta solo para probar migraciones (I-02) y se
  deja dormir. Usar etiquetas `vYYYY.MM.DD` para dar nombre a cada release.

### BAJO

**I-16 · `workers = 0`: los límites de Odoo no se aplican.**
- `entrypoint.sh:42` (`workers = 0`) y `:45` (`limit_time_real`): en modo multihilo de Odoo los límites
  `limit_time_*`/`limit_memory_*` **no se imponen** (solo aplican con `workers > 0`; *por verificar* en
  Odoo 19). Un informe o una exportación grande puede consumir toda la memoria del contenedor y este se
  reinicia (pierde sesiones). Además los crons corren en el mismo proceso/GIL que la web
  (`max_cron_threads`, `:43`).
- Es decisión documentada (un solo puerto para HTTP+websocket), y con `workers>0` el websocket va en
  otro puerto (`gevent_port`/`longpolling`), lo que el contenedor de Cloudflare (un puerto por
  `defaultPort`) complicaría. Mantener `workers=0` es razonable para este tamaño; medir memoria y
  añadir límites al nivel del contenedor (el tamaño) y del lado de la tarea pesada (paginar exportaciones).

**I-17 · Reproducibilidad: piezas flotantes.**
- Bien: `vendor/odoo` fijado por commit (`.gitmodules` + submódulo), `wkhtmltopdf` con versión fija
  (`Dockerfile:31`), `package-lock.json` y `npm ci`.
- Flotante: `ubuntu:24.04` por tag (`Dockerfile:7`), paquetes apt sin versión, `pip install -r
  vendor/odoo/requirements.txt` (rangos de Odoo, sin `--require-hashes`; `Dockerfile:16-19`),
  `postgres:16` (`docker-compose.yml:8`, CI) mientras Neon usa su versión por defecto (*por verificar*; usar
  la misma mayor en Neon, CI y compose), `cloudflare/cloudflared:latest` (`docker-compose.yml:44`) y
  `cloudflared/releases/latest` sin verificar hash (`preview.yml:67`), `ruff` sin versión (`ci.yml:29`).
- Arreglo: fijar la imagen base por digest (Dependabot/Renovate la actualiza), generar un
  `requirements.lock` con `pip-compile`/`uv` para la imagen, fijar `ruff`, versión de `cloudflared`
  con checksum.

**I-18 · Seguridad de los workflows.**
- Bien: `permissions: contents: read` por defecto (`ci.yml:17-18`), sin `pull_request_target`, secretos
  solo en el job `deploy` bajo `environment: production`, valores enmascarados por GitHub.
- Mejorable: acciones por tag móvil (`actions/checkout@v4`, `docker/build-push-action@v6`,
  `ci.yml:25,117,119`…) en lugar de SHA; sin `.github/dependabot.yml` (solo existe la plantilla de PR);
  sin revisores requeridos en el environment `production` (configurar en GitHub); sin análisis de
  imagen (Trivy/Grype), `hadolint` ni `shellcheck` del `entrypoint.sh`; el token de Cloudflare de
  `DESPLIEGUE.md` §2 incluye "Containers: Edit" (correcto) — acotarlo a la cuenta y al Worker
  (*por verificar* permisos mínimos vigentes).

**I-19 · `preview.yml`: código muerto y entradas sin validar.**
- `preview.yml` solo dispara con `workflow_dispatch` (líneas 13-19), pero el paso "Publicar el link en
  el PR" exige `github.event_name == 'pull_request'` (línea 117): **nunca se ejecuta**; `pull-requests:
  write` (21-23) sobra. `inputs.minutos` no se valida como número (`:173`, `[ "$MIN" -gt 60 ]` falla
  con texto; no hay inyección porque pasa por `env`).
- Duración: `sleep` hasta 60 min (`:176`) + construcción (10–15 min sin caché) + Playwright dentro de un
  `timeout-minutes: 90` (`:33`): justo, sin margen si la caché falla. El repositorio es público (lo dice el
  propio workflow), así que los minutos de Actions son gratis; si pasara a privado, una sola
  previsualización de 60 min cuesta minutos de la cuota (*por verificar* cuota vigente de GitHub).
- El fallback sin `PREVIEW_ADMIN_PASSWORD` imprime la clave de admin en un log público (`:79-83`,
  `:162`): decisión documentada y limitada a una base efímera; correcta, pero vale recordar que el túnel
  `trycloudflare.com` es público mientras dura.
- Arreglo: borrar el paso de PR y el permiso (o cambiar el disparador), validar el número
  (`[[ $MINUTOS =~ ^[0-9]+$ ]]`), subir `timeout-minutes` a 120 o bajar el tope.

**I-20 · TLS a la base sin verificación del certificado.**
- `docker-compose.yml`/`entrypoint.sh:35` y `wrangler.jsonc:35`: `sslmode=require` cifra pero no
  verifica el servidor. Neon presenta certificado de CA pública; `verify-full` es viable con
  `PGSSLROOTCERT=system` en libpq 16 (Ubuntu 24.04, `libpq5` ya instalado) — *por verificar* que
  psycopg2 de Odoo 19 lo respete. Riesgo bajo (tráfico dentro de la red de Cloudflare a Neon por
  internet público, sin MITM conocido); mejora barata.

**I-21 · CI: tiempos y caché (sin problema grave).**
- Los 4 jobs corren en paralelo (bien). `odoo-tests` (`ci.yml:46-81`) instala todos los módulos desde
  cero y `docker` (`:100-145`) vuelve a instalarlos: dos instalaciones completas de 8 módulos por
  ejecución. Una posible optimización: una sola instalación para ambos, o cachear el volcado de la base
  de módulos base. No se ve en el repo una medición de tiempos; medir antes de optimizar.
- `type=gha,mode=max` (`:125-126`): con capas de 1–2 GB puede chocar con el límite de caché de GitHub
  por repositorio (10 GB *por verificar*); `scope` distinto para CI y preview.
- El submódulo (`submodules: true`, `.gitmodules` `shallow = true`) se baja en cada job sin caché.
- No se prueba la ruta de **actualización** (`-u` sobre una base existente con datos de la versión
  anterior); el humo solo cubre base nueva (`ci.yml:127-143`). Añadir un job que instale el SHA anterior
  de `main`, cargue algo y actualice al nuevo (caso real de cada deploy).

**I-22 · Menores.**
- `docker/entrypoint.sh:90`/`Dockerfile:61`: `tini` sin `-g`; durante el `-u` el proceso hijo no recibe
  la señal de apagado (la ejecuta `bash`, no `exec`). Usar `tini -g --` o `exec` en la función `odoo`
  donde sea posible.
- `Dockerfile:59-60` `HEALTHCHECK`: Cloudflare Containers probablemente no lo usa (la sonda es
  `pingEndpoint`; *por verificar*): sirve para Docker/CI, inocuo.
- `edge/src/index.ts:63`: `envVars` incluye `DB_PASSWORD` aunque el secreto falte (undefined) → error
  tardío en el contenedor en lugar de un fallo claro en el Worker. Añadir validación y una prueba unitaria
  de `OdooContainer` (hoy solo se prueban `routing.ts`/`handler.ts`).
- `scripts/test.sh:40`: detecta fallos por `ERROR|CRITICAL` en el log porque `odoo-bin` no siempre sale
  ≠ 0: sólido y bien razonado; las advertencias esperadas de Odoo podrían dar falsos positivos (aún no
  vistos; no hay evidencia).
- `caches.default` (`index.ts:86`) solo funciona en dominios propios, no en `*.workers.dev` (*por
  verificar*): mientras no esté `dcasapty.com`, el caché del borde no actúa.
- `Makefile:14`: `make lint` usa `.venv/bin/ruff`; `make edge-test` y `test` ok. Sin `make image`/`backup`.

## 3. Lo que está bien hecho (conservar)

- **Imagen**: multi-etapa (compiladores fuera de la imagen final, `Dockerfile:10-19`), traducciones
  innecesarias eliminadas con el truco correcto (`COPY --from` toma el estado ya limpio), `tini` como PID 1,
  `USER odoo` no-root con shell `nologin` (`:49,56`), orden de capas que aprovecha la caché
  (`addons` al final), `.dockerignore` que deja fuera `up media`, `edge`, `docs`, `.git`.
- **Sin secretos en la imagen**: `odoo.conf` generado al arrancar con `chmod 600`
  (`entrypoint.sh:87-111`), variables obligatorias con `:?`, `list_db = False`, `dbfilter` anclado,
  `proxy_mode`, `unaccent` con extensión creada de forma idempotente, advertencia si falta la pimienta.
- **Arranque idempotente**: versión desplegada en `ir_config_parameter`, reinicios normales no actualizan,
  admin nunca queda `admin/admin` (`:64-72`).
- **Worker**: decisiones aisladas y testeadas (`routing.ts`, `handler.ts`); caché solo de respuestas
  `public` sin `Set-Cookie` (`routing.ts:48-53`); rutas de Brian nunca en caché; 308 para no perder el
  cuerpo de un POST; bloqueo del gestor de bases; cabeceras de seguridad; se omite la reconstrucción de
  WebSocket (101); `migrations` con `new_sqlite_classes` correcto para Containers.
- **Neon directo, no pooler** por `LISTEN/NOTIFY`: decisión correcta y documentada
  (`DESPLIEGUE.md` §1). Con el pooler en modo transacción se rompe el bus de Odoo.
- **CI**: permisos mínimos, concurrencia (sin cancelar `main`), humo de imagen contra base vacía con
  comprobación de la marca, artefacto de log en fallo, despliegue condicionado a todos los jobs y a
  `main`, *guard* que permite que los tests corran sin secretos, dependencias del borde con `npm ci` y
  lockfile. La pimienta "se crea una vez, nunca se sobrescribe" es un buen patrón.
- **Documentación honesta**: `DESPLIEGUE.md` ya explica la alternativa sin Containers (VPS + túnel) con
  la misma imagen. El diseño **no ata los datos a Cloudflare** ("nada de negocio vive fuera de la base"),
  lo que hace barata cualquier migración posterior.

## 4. Arquitectura recomendada, dimensionamiento y costos

### 4.1 Arquitectura (se mantiene la actual con cambios puntuales)

```
Cliente ─► Worker "dcasa" (caché, bloqueos, headers, 503 amable)
              └─► DO OdooContainer (locationHint enam, 1 instancia) ─► Container Odoo 19
                                                                     │ TLS, conexión directa
   GitHub Actions ──(1) build imagen una vez, push, digest           ▼
        ├─(2) rama/snapshot Neon + `odoo -u` (job de migración)   Neon PostgreSQL (mismo mayor que CI)
        ├─(3) wrangler deploy (mismo digest)                      ├ datos + adjuntos (filestore en BD)
        └─ diario: pg_dump → age → R2 (ciclo de vida)             └ PITR + ramas (staging efímero)
   Monitor externo (health + /shop) ─► aviso al dueño
```

- **Filestore: base de datos por ahora, R2 después.** Con ~200 productos y 323 fotos (31 MB en módulo) la
  base queda en cientos de MB; meter adjuntos en Postgres es lo más simple y hace el `pg_dump` un respaldo
  completo. Riesgos: crecimiento de almacenamiento y de transferencia (cada `web/image` lee un `bytea`),
  PITR más pesado. Umbral para pasar a R2: adjuntos > ~2–3 GB, o facturación de Neon dominada por
  almacenamiento. Odoo Community no trae almacenamiento S3: hay que escribir un módulo que sobreescriba
  `ir.attachment._file_read/_file_write/_file_delete` contra R2 (API S3) o adoptar uno de OCA
  (*por verificar* versión 19). **No recomendado ahora**: añade latencia y un punto de fallo; R2 sí es
  el sitio correcto para **respaldos** y para los originales de `up media`.
- **Sesiones**: aceptar su pérdida (I-04) y reducir causas (menos deploys). Nunca >1 instancia sin resolverlo.
- **Cron de Odoo**: corre dentro del contenedor (un hilo, `max_cron_threads=1`); el cron del Worker solo
  lo mantiene despierto. Las tareas de D'CASA (`dcasa_socios` cada hora) y correos necesitan el
  contenedor encendido: con reposo nocturno, no corren de noche.
- **Workers/websocket**: `workers=0` mantiene HTTP+WebSocket en 8069, compatible con un solo puerto
  de Containers; el Worker ya no reconstruye respuestas 101. El WebSocket cuenta como conexión
  abierta en el Durable Object mientras dure (duración facturable, *por verificar* cómo interactúa con
  `sleepAfter`); con 1–5 usuarios de backend es marginal.
- **Límites de Containers a verificar con el MCP**: tamaños/tipos de instancia y su disco, número máximo
  de instancias, tiempo de gracia de SIGTERM, reinicios por mantenimiento, tope de tamaño de imagen, si
  hay disco persistente (hoy se asume que no), región de ubicación, y si los logs del contenedor se
  conservan.
- **Entornos**: producción + staging efímero (rama de Neon y `env.staging`, §I-15). Desarrollo local
  con `docker compose` (ya funciona).

### 4.2 Dimensionamiento

- Odoo threaded sin workers, 8 módulos + website + eCommerce: memoria base típica de 0,8–1,5 GiB
  (estimación, sin medir). **4 GiB (`standard-1`) debería alcanzar**; `standard-2` (6 GiB) da holgura para
  informes/exportaciones. Medir RSS en un entorno de prueba con el catálogo cargado y decidir.
- 1 vCPU vs 0,5 vCPU: Python con GIL no aprovecha más de un núcleo; 0,5 vCPU (`standard-1`) puede
  volver lentos los renders del sitio bajo carga. Medir TTFB en `/shop` (ver I-05).
- `db_maxconn = 16` (`entrypoint.sh:44`) es correcto para una instancia; el tope de conexiones de Neon
  depende del tamaño del cómputo (*por verificar*) y queda muy por encima.

### 4.3 Costo mensual estimado (mes de 30 días = 720 h)

**Supuestos**: tarifas de Containers (memoria ≈ $0,0000025/GiB·s; CPU ≈ $0,000020/vCPU·s solo por uso
activo; disco ≈ $0,00000007/GB·s; cuota mensual incluida ≈ 25 GiB·h, 375 vCPU·min, 200 GB·h) y de Neon
(cómputo ≈ $0,106/CU·h, almacenamiento ≈ $0,35/GB·mes, mínimo ≈ $5 en plan de pago, 0,25 CU mínimo en
autosuspend activo) son **de mi memoria: por verificar con el MCP de Cloudflare y la consola de Neon**.
CPU media del 10 % del vCPU asignado; tráfico bajo (≪ 10 M solicitudes/mes, sin costo extra de Worker).

| Escenario | Contenedor | Plan Workers | Neon | R2 (respaldos) | **Total** |
|---|---|---|---|---|---|
| A. Actual: `standard-2` 24/7 (cron 10 min) | ≈ $45 | $5 | ≈ $19 (0,25 CU × 720 h) | ≈ $0 | **≈ $70** |
| B. `standard-1` 24/7 | ≈ $29 | $5 | ≈ $19 | ≈ $0 | **≈ $53** |
| C. `standard-1`, activo ~12 h/día (sin keep-alive nocturno) | ≈ $15 | $5 | ≈ $10 (autosuspend) | ≈ $0 | **≈ $30** |
| D. VPS + túnel (alternativa, §4.4) | ≈ $5–12 (VPS) | $0 (túnel gratis) | $0 (PG local) | ≈ $0 | **≈ $6–12** |

Cómo sale A (memoria): 6 GiB × 720 h = 4.320 GiB·h − 25 incluidas = 4.295 × 3.600 s × $2,5e-6 ≈ $38,7;
disco 12 GB ≈ $2,1; CPU 10 % de 1 vCPU ≈ $4,7 tras la cuota → ≈ $45,5.
Notas: (1) el plan gratuito de Neon (*por verificar*: ~100 CU·h/mes) **no alcanza** con Odoo conectado
24/7 porque Odoo consulta la base cada ~60 s por su hilo de cron y mantiene conexión de bus; al agotarse
el cómputo gratuito la base se suspende y el sitio cae: no usarlo en producción. (2) Con escenario C
los crons de Odoo solo corren con el contenedor despierto y el primer visitante de la mañana paga el
arranque en frío (decenas de segundos, posiblemente más si también despierta Neon). (3) R2 para
respaldos diarios de pocos cientos de MB con 7/4/12 retenciones cabe en la capa gratuita (10 GB,
*por verificar*); no hay cargos de salida. (4) Solicitudes del Worker y Durable Object del proxy, y
salida de red del contenedor, son despreciables a este volumen (*por verificar* cuota de salida).
**El presupuesto "$5 + $1 + R2" cubre solo el Worker y R2; no el contenedor ni, en general, Neon.**

### 4.4 Alternativa si el presupuesto es ≤ ~$10/mes

`docker compose` ya definido en el repo + VPS de 4 GB con PostgreSQL local (latencia ≈ 0, sin sesiones
perdidas porque el disco es persistente: los adjuntos pueden ir en filestore y las sesiones sobreviven a
deploys) + Cloudflare Tunnel (gratis) para el dominio, la caché y WAF, + `pg_dump` diario a R2.
Costos de operación: parches del sistema, disco y un único punto de fallo (mitigado con respaldos
restaurables). Es la opción más barata y la de mejor rendimiento de Odoo; la decisión es de negocio.

## 5. Checklist de migración a Cloudflare

Marcar con `[ ]`; lo que requiera el MCP de Cloudflare está indicado.

**Antes de pagar nada**
- [ ] El dueño elige escenario A/B/C/D (§4.3) con los precios verificados (MCP).
- [ ] Verificar con el MCP: tipos de instancia y precios de Containers, cuota incluida, regiones, límite
      de imagen, SIGTERM/gracia, logs del contenedor, `wrangler containers push`, `deploy --secrets-file`.
- [ ] Crear proyecto Neon (región y versión de PG iguales a CI/compose), plan de pago si el
      contenedor corre 24/7; verificar retención de PITR, límite de conexiones y autosuspend.
- [ ] Medir RTT contenedor↔Neon y TTFB de `/`, `/shop`, `/web/login` en un entorno de prueba (I-05).

**Código/CI (cambios propuestos; la auditoría no los aplica)**
- [ ] Mover migraciones fuera del arranque (I-02) + rama de Neon previa + `-u all` si cambió `vendor/odoo` (I-10).
- [ ] Reintentos y aborto en `sql()` del entrypoint (I-06).
- [ ] Un solo build → push → deploy por digest (I-08); `paths:` en deploy.
- [ ] Guard con validación de `DB_HOST`/secretos no vacíos (I-11); eliminar `CAMBIAR.neon.tech`.
- [ ] 503 amable + `Retry-After` en el Worker; log del cron (I-07, I-12).
- [ ] `sparse-checkout` sin `up media` en CI (I-09).
- [ ] Workflow de `pg_dump` cifrado → R2 + restauración de prueba (I-03).
- [ ] Dependabot, acciones por SHA, Trivy/hadolint/shellcheck (I-17, I-18).
- [ ] `preview.yml`: limpiar paso de PR y validar entrada (I-19).
- [ ] Prueba de actualización `-u` sobre base de la versión anterior en CI (I-21).

**Secretos y configuración**
- [ ] Cuenta Cloudflare (Workers Paid), token con el mínimo de permisos, `CLOUDFLARE_ACCOUNT_ID`.
- [ ] Environment `production` con **revisores requeridos**; secretos: `DB_PASSWORD`, `ODOO_ADMIN_PASSWORD`
      (maestra), `ADMIN_USER_PASSWORD` distinto (I-13), `DCASA_PIN_PEPPER` con copia offline (I-14),
      claves de Brian.
- [ ] Variables: `DB_HOST` (directo), `DB_USER`, `DB_NAME`, `CANONICAL_HOST`.
- [ ] `sslmode=verify-full` si se confirma soporte (I-20).

**Puesta en marcha**
- [ ] Inicializar la base **fuera** del primer request (DESPLIEGUE §4) y verificar admin, español, `unaccent`.
- [ ] Desplegar en `*.workers.dev`, probar `/shop`, `/socios`, `/web/login`, websocket (chat de Brian/bus).
- [ ] Migrar datos (Fase 2 del plan) con un `pg_dump` de respaldo previo y una rama de Neon como ensayo.
- [ ] Mover DNS de `dcasapty.com` a Cloudflare, activar `routes`, `web.base.url`, verificar que los QR
      de socios apuntan al dominio canónico; cache del borde empieza a funcionar (I-22).
- [ ] Monitor externo + alertas activas antes de anunciar (I-12).
- [ ] Ensayar una restauración completa (Neon + pimienta + secretos) y anotar RTO real.

**Operación**
- [ ] Runbook: desplegar fuera de horario de venta, rollback = restaurar rama/PITR + redeploy del SHA
      anterior **con migración desactivada**, rotación de claves, qué hacer si el contenedor no levanta.
- [ ] Revisar costos reales del primer mes contra §4.3 y ajustar `instance_type`/`sleepAfter`.

## 6. Plan de arreglo (orden sugerido)

1. Decisión de costo/escenario con el dueño (I-01) y medición de latencia (I-05): condiciona todo.
2. Respaldo independiente + ensayo (I-03) y copia de la pimienta (I-14): antes de cargar datos reales.
3. Migraciones fuera del arranque + rama previa (I-02, I-06, I-10).
4. CI: build único, guard, `paths`, `sparse-checkout` (I-08, I-09, I-11).
5. Observabilidad y 503 amable (I-07, I-12).
6. Endurecimiento y reproducibilidad (I-13, I-17, I-18, I-20) y limpieza (I-19, I-22).
7. Staging efímero (I-15) y prueba de actualización en CI (I-21).

## 7. Pendiente / por verificar

- Todo precio/límite de Cloudflare y Neon (§4.3, §4.1).
- Comportamiento de Odoo 19 (vendor vacío): precarga del registro vs `/web/health`, límites con
  `workers=0`, servicios `db` de `/jsonrpc`, lectura de `PGSSLROOTCERT` por psycopg2.
- Coordinación con `seguridad`: I-13, I-14, I-18, I-20 (ver bitácora).
