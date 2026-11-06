# Despliegue en Cloudflare

Arquitectura elegida (opción A, `docs/auditoria/DECISION_Y_PLAN.md`): **un Container (`standard-1` en producción, `basic` en staging) de
Cloudflare con Odoo y PostgreSQL 16 adentro**. El disco del contenedor es efímero, así que la base
vive protegida por **pgBackRest**, que manda el WAL (cada cambio) a un bucket de **R2** de forma
continua (RPO aceptado ≈ 1 min), más un respaldo lógico diario (`pg_dump` cifrado, 03:17 de Panamá)
también a R2. Si el contenedor se reinicia o cambia de máquina, al arrancar restaura la base desde R2
antes de abrir el puerto. Contrato entre el Worker y la imagen: `edge/CONTRATO_CONTENEDOR.md`.

Para el dueño, en lenguaje claro (costos, primer despliegue, simulacros, qué hacer si el sitio cae,
cómo restaurar): **[docs/OPERACION.md](OPERACION.md)**. Este documento es la referencia técnica y **el único lugar con
la receta de producción** (LEEME_PRIMERO, OPERACION y el README remiten aquí).

## La receta de producción

Puesta al día el 2026-11-06. Es el camino que se usó en los despliegues a producción 31 a 47 (del 2026-10-27 al
2026-11-05). Producción sirve `https://dcasapty.com` desde el 2026-10-27. Antes de empezar, leer
[CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md) (cada falla ya pagada) y tener el «sí» de la dueña (LEEME_PRIMERO §2).

1. **En la rama de trabajo**, el cambio con su prueba. En local: `scripts/test.sh <módulos>`, `ruff check addons` y, si
   tocó un Worker, `npm test && npm run typecheck` en su carpeta.
2. **CI/CD a mano en la rama** (*Actions › CI/CD › Run workflow*, la rama de trabajo, `desplegar_en = staging`). Corre
   todas las pruebas, construye la imagen una vez, la despliega a staging y después despliega Juan a staging. Tarda unos
   **45 minutos** (CI #260 del 2026-11-05: ~25 min de pruebas de Odoo, ~20 min del despliegue a staging, ~1 min de Juan).
   - Si el despliegue a staging se frena en el **respaldo previo** (staging apagado, HTTP 000 o 503, o un 429 de R2), la
     imagen ya está construida y probada: lanzar *Desplegar* a `staging` con su `imagen_digest` en vez de repetir el CI
     (así salieron Desplegar 34, 38, 40 y 44).
3. **Anotar los dos datos de esa ejecución:** el `imagen_digest` (`sha256:…`) que deja el registro o el resumen del job
   de staging, y el commit probado (el SHA de 40 caracteres de la punta de la rama sobre la que corrió el CI). Nunca
   inventar ni «completar» un SHA.
4. **PR a `main`** con ` [skip ci]` al final del título (plantilla `.github/pull_request_template.md`). Unir con
   *squash* y `expectedHeadSha` = el commit probado (herramienta `mcp__github__merge_pull_request`). Entre el CI y el
   *squash* **no se sube nada** a la rama: lo nuevo, sin probar, se colaría a `main`.
5. **Comprobar el árbol:** `git fetch origin` y `git rev-parse origin/main^{tree}` tiene que ser igual a
   `git rev-parse <commit probado>^{tree}`. Si no, parar.
6. **Desplegar desde `main`** (*Actions › Desplegar › Run workflow*, rama `main`): `entorno = production`, el
   `imagen_digest` del paso 3, `app_version` = **el commit probado** (40 caracteres; nunca el SHA del *squash*: esa
   etiqueta no existe en el registro) y `respaldo_previo = true`. Tarda unos **15 minutos**, contando los 600 s de
   vigilancia del final (`.github/scripts/esperar_salud.sh`).
   - Un 429 de R2 en el respaldo previo frena sin tocar producción: volver a lanzarlo. Un 503 «Odoo apagado»: esperar al
     minuto 7 de la hora siguiente (el cron lo despierta) y volver a lanzarlo. Sin respaldo, solo con el «sí» de la dueña.
7. **Mirar la salud:** `https://dcasapty.com/dcasa/salud` con `version` = los 12 primeros del `app_version`,
   `base_al_dia: true` y `humo` en orden; y abrir el Inicio.
8. **Cancelar el CI que abrió el PR** (corre otra vez las mismas pruebas sobre el mismo árbol).
9. **Traer `main` a la rama:** `git merge -s ours origin/main` (con el árbol ya comprobado en el paso 5) y subir. Un merge
   normal choca en archivos falsos porque `main` se une por *squash*.
10. **Juan:** *Actions › Desplegar Juan*, `entorno = production`, sin `dry_run`, **solo si cambió `juan/`**.
11. **Anotar:** la bitácora de LEEME_PRIMERO, PRIORIDADES y el historial de despliegues de CONTEXTO_AGENTICO.

**La alternativa** que el flujo todavía permite: *CI/CD › Run workflow* en `main` con `desplegar_en = produccion`. Vuelve
a correr todas las pruebas sobre `main` (otra imagen, otro SHA) y despliega solo `dcasa` (no Juan); desde otra rama falla
a propósito. No es la que se usa: tarda más y no despliega la imagen que ya se vio en staging.

**Volver atrás:** §5 y [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md) (ojo: las estables 1 y 2 son anteriores al dominio
propio y a 8 módulos).

## 1. El camino de un cambio hasta producción

`.github/workflows/ci.yml` corre en cada PR, en cada push a `main` y a mano. **Un push a `main` solo corre las
pruebas: a ningún entorno se despliega solo.**

| Job | Qué hace |
|---|---|
| `lint` | ruff, XML, shellcheck (`docker/`, `scripts/`, `.github/scripts/`) y actionlint |
| `odoo-tests` | instala los módulos en una base limpia y corre los tests |
| `edge` | typecheck y tests del Worker |
| `docker` | **construye la imagen una sola vez**, la arranca con su PostgreSQL interno contra un S3 local (moto), prueba el sitio, `admin/admin`, y que el WAL llegue al bucket. Si la ejecución va a desplegar, guarda **esa** imagen como artefacto (dura 1 día; si el espacio de GitHub se llena, ver «Limpiar copias temporales» en [OPERACION.md](OPERACION.md)) |
| `simulacro-restauracion` | `scripts/simulacro_restauracion.sh`: carga, mata PostgreSQL, borra el disco, restaura desde S3 y compara. Falla si el RPO pasa de 90 s o hay filas distintas/corruptas |
| `desplegar-produccion` | solo *Run workflow* con `desplegar_en = produccion`, **desde `main`**, y solo si **todo** lo anterior pasó. Desde otra rama falla con un aviso (`produccion-solo-desde-main`) |
| `desplegar-staging` | solo *Run workflow* con `desplegar_en = staging` (cualquier rama) |

Los dos despliegues usan `.github/workflows/desplegar.yml`, que en este orden:

1. **Valida** que todos los secretos y variables del environment existen, no están vacíos ni tienen
   marcadores (`CAMBIAR`, `PENDIENTE`, `<...>`), que las claves largas tienen ≥ 32 caracteres y que la
   contraseña maestra es distinta de la de `admin` (I-11). También rechaza un `edge/wrangler.jsonc` con
   variables marcador. Si falta algo, **no toca Cloudflare**. (En cada PR, el job `edge` ya genera la
   configuración de despliegue de los dos entornos y la valida con `wrangler deploy --dry-run`.)
2. **Sube la imagen probada** al registro de Cloudflare (`wrangler containers push`), después de
   comprobar que su ID es el mismo que pasó la prueba de humo (I-08). Nada se reconstruye.
3. **Genera la configuración** (`edge/wrangler.desplegar.json`, solo en el runner) con la imagen fijada
   a esa referencia de registro: `registry.cloudflare.com/<cuenta>/dcasa-odoo:<SHA>` con la política
   `default` elegida (si algún día se pasa a `durable_object`, el mismo script la fija por digest), y
   la valida con `wrangler deploy --dry-run`.
4. **Prepara los secretos** que viajan con el despliegue (incluido `R2_ENDPOINT`, que se arma con el
   Account ID). `DCASA_PIN_PEPPER` y `PGBACKREST_CIPHER_PASS` se suben **solo si el Worker todavía no
   los tiene** (nunca se rotan).
5. **Respaldo previo**: `POST <URL_SITIO>/__edge/respaldo` con `RESPALDO_TOKEN`, si el Worker ya
   existe. El borde corre `dcasa-respaldo` dentro del contenedor y responde al terminar. Si falla, no
   se despliega (I-02, ver §5). En staging, si Odoo está dormido (503), se sigue con un aviso.
6. `wrangler deploy --secrets-file … --env=""` (producción) o `--env=staging`: código del Worker,
   imagen y secretos **en una sola versión**. Los secretos quedan cargados antes de que arranque el
   contenedor nuevo (sin los de R2 y cifrado, el Worker ni lo enciende).
7. **Espera** a que `GET /__edge/health` dé 200 (hasta 20 min: primero ve detenerse la instancia
   vieja, luego el contenedor nuevo restaura desde R2 y corre la actualización de módulos).
8. Deja en el resumen de la ejecución el **digest de la imagen** y el SHA, para poder volver atrás.

Acciones de GitHub fijadas por SHA; `.github/dependabot.yml` propone cada lunes las actualizaciones de
acciones, de `edge/` (npm) y de la imagen base (docker). Esos PR pasan por todo el CI.

`.github/workflows/preview.yml` (a mano) levanta la misma imagen con datos de demostración y un túnel
temporal; no toca ningún entorno.

## 2. Cloudflare (una vez)

1. Cuenta con plan **Workers Paid** ($5/mes; necesario para Containers).
2. **R2**: dos buckets, `dcasa-respaldos` (producción) y `dcasa-respaldos-staging`, con la pista de
   ubicación **Este de Norteamérica (ENAM)**, la misma región que el contenedor. Un **token de R2** por
   bucket con permiso *Object Read & Write* limitado a ese bucket: da `Access Key ID` y
   `Secret Access Key`. Paso a paso en `docs/OPERACION.md` → «Crear los buckets de R2».
3. **API token** de cuenta para GitHub Actions (*Manage Account → Account API Tokens*): Workers con
   rol de administrador a nivel de producto (crear un Worker nuevo —`dcasa`, `dcasa-staging`— lo exige),
   *Containers: Edit* y *Account Settings: Read*; con el dominio propio (desde el 2026-10-26), *Zone → Workers Routes →
   Edit* para `dcasapty.com`. *Por verificar al crearlo*: los nombres exactos de los permisos cambian;
   si `wrangler containers push` o `wrangler deploy` dan error de autorización, el mensaje dice cuál falta.
4. Anotar el **Account ID**.

## 3. GitHub: environments, secretos y variables

*Settings → Environments*: crear **`staging`** y **`production`**. En `production`, en *Deployment branches and
tags*, elegir *Selected branches* y permitir solo `main`.

**No se usan «Required reviewers».** Cuando se armó esto, el repositorio era privado y el plan no los ofrecía; desde
el 2026-10-13 el repositorio es público, pero no se configuraron. La aprobación es el **clic de quien lanza el
despliegue** (*Desplegar* en `main`, o *CI/CD* con `desplegar_en = produccion`); por eso un merge nunca despliega solo. Una prueba
(`edge/test/despliegue-produccion.test.ts`) falla si alguien vuelve a enganchar producción a un push.

Cada environment lleva **sus propios** valores (staging nunca comparte bucket, token de respaldo ni
clave de cifrado con producción):

| Tipo | Nombre | Obligatorio | Valor |
|---|---|---|---|
| Secret | `CLOUDFLARE_API_TOKEN` | sí | token del §2.3 |
| Secret | `CLOUDFLARE_ACCOUNT_ID` | sí | account id |
| Secret | `R2_ACCESS_KEY_ID` | sí | del token de R2 del bucket de ese entorno |
| Secret | `R2_SECRET_ACCESS_KEY` | sí | ídem |
| Secret | `PGBACKREST_CIPHER_PASS` | sí | `openssl rand -hex 32`; **copia en el gestor de contraseñas**. Cifra los respaldos en R2: **jamás se rota** (perderla = respaldos ilegibles). Se sube al Worker una sola vez |
| Secret | `RESPALDO_TOKEN` | sí | `openssl rand -hex 32`; autoriza el endpoint de respaldo del Worker |
| Secret | `ODOO_ADMIN_PASSWORD` | sí | clave del usuario `admin` de Odoo (larga y aleatoria) |
| Secret | `ODOO_MASTER_PASSWORD` | sí | contraseña maestra (`admin_passwd`), **distinta** de la anterior |
| Secret | `DCASA_PIN_PEPPER` | sí | pimienta del PIN de socios (ver abajo); **jamás se rota** |
| Secret | `BRIAN_API_KEY` | sí | clave del proveedor de IA de Brian (en staging, una clave de pruebas con tope de gasto) |
| Secret | `RESEND_API_KEY` | no | clave de Resend (permiso «solo envío»; otra para staging): sin ella no sale ningún correo. Se sube con cada despliegue. Ver [CORREO.md](CORREO.md) |
| Secret (solo panel) | `RESEND_CAMPANAS_API_KEY` | no | clave de **campañas** de Resend (permiso «Full access»: contactos, segmento y broadcasts), aparte de la de facturas. La dueña la pega como secreto en el panel de Cloudflare del Worker `dcasa` (no está en GitHub ni en el flujo de despliegue: los despliegues no la tocan). Sin ella no sale ninguna campaña. Ver [CAMILA.md](CAMILA.md) §6 |
| Secret | `META_CAPI_TOKEN` | no | token de la Conversions API de Meta (Administrador de eventos › el píxel › Configuración › «Generar token de acceso»): sin él no sale ninguna venta hacia Meta. Se sube con cada despliegue; vacío no se sube. Odoo lo lee del entorno al enviar y nunca lo guarda. Ver [META_EVENTOS.md](META_EVENTOS.md) |
| Secret | `TELEGRAM_BOT_TOKEN`, `BRIAN_TELEGRAM_SECRETO` | no | ver «Brian» |
| Secret | `TIENDA_FEED_TOKEN` | no (sí para la caché de páginas) | `openssl rand -hex 32` (≥ 32 caracteres), **distinto por entorno**. Lo comparten el Worker y Odoo: con él Odoo certifica las páginas anónimas que el borde guarda y protege el aviso de invalidación. Se puede rotar (se sube en cada despliegue). Ver edge/CONTRATO_CONTENEDOR.md §5 |
| Secret | `DCASA_PUERTA_RUTA`, `DCASA_PUERTA_SECRETO`, `DCASA_ACCESS_EQUIPO`, `DCASA_ACCESS_AUD` | no (las cuatro juntas para la puerta del equipo) | Ver docs/SEGURIDAD_ACCESO.md §8.4: la ruta secreta de la entrada (`/entrada-…`), `openssl rand -hex 32` (≥ 32, **distinto por entorno**), `https://<equipo>.cloudflareaccess.com` y el *AUD Tag* de la aplicación de Cloudflare Access. Si falta alguna, la puerta queda apagada |
| Variable | `URL_SITIO` | sí | dirección pública del Worker, sin `/` final: en producción `https://dcasapty.com` (desde el 2026-10-26); staging: `https://dcasa-staging.<subdominio>.workers.dev` (o `https://staging.dcasapty.com` cuando exista) |
| Variable | `CANONICAL_HOST` | no | pisa el de `edge/wrangler.jsonc` (`dcasapty.com` / `staging.dcasapty.com`). **Vacía = se usa el anfitrión de `URL_SITIO`**: Odoo arma con este dominio las direcciones de las fotos de productos, del PDF de una cotización y de los webhooks, así que tiene que ser donde el sitio de verdad responde (si apuntara a `staging.dcasapty.com` sin que exista, Telegram no podría bajar la foto ni el PDF) |
| Variable | `R2_ENDPOINT` | no | solo si el bucket está en otra jurisdicción; por defecto `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| Variable | `BRIAN_PROVEEDOR`, `BRIAN_MODELO`, `BRIAN_BASE_URL` | no | ver «Brian» |

En el Worker, `ODOO_ADMIN_PASSWORD` se carga con el nombre `ADMIN_PASSWORD`, y `R2_ENDPOINT` como
secreto (lleva el Account ID). `R2_BUCKET`, `CANONICAL_HOST`, `DCASA_ENTORNO`, `DCASA_STOCK_PRUEBA` (`0` en producción, `10` en staging) y `ODOO_DORMIR_TRAS` son
`vars` de `edge/wrangler.jsonc`, una sección por entorno. Ya no hay `DB_HOST`/`DB_USER`/`DB_NAME`/
`DB_PASSWORD` ni Neon: PostgreSQL vive dentro del contenedor y su configuración la decide la imagen.

Si un environment no tiene **ningún** secreto, su despliegue se omite con un aviso (los tests igual
corren). Si tiene alguno, se exigen todos los obligatorios.

### Brian, el asistente

Brian queda instalado; sin `BRIAN_API_KEY` el despliegue no avanza (es obligatorio desde la Fase 1).
Las variables opcionales:

| Tipo | Nombre | Valor |
|---|---|---|
| Variable | `BRIAN_PROVEEDOR` | `anthropic`, `openai`, `xai`, `groq`, `openrouter` u `ollama` |
| Variable | `BRIAN_MODELO` | opcional con Anthropic (por defecto `claude-sonnet-5-5`) |
| Variable | `BRIAN_BASE_URL` | solo para proveedores OpenAI-compatibles propios |
| Secret | `TELEGRAM_BOT_TOKEN` | token del bot (@BotFather) |
| Secret | `BRIAN_TELEGRAM_SECRETO` | `openssl rand -hex 32`: ruta y encabezado del webhook de Telegram |
| Text | `BRIAN_TELEGRAM_CHATS` | IDs de los chats de Telegram a los que Brian atiende (coma); con ella puesta, de cualquier otro chat no contesta nada (docs/BRIAN.md) |

El Worker pasa al contenedor solo los que existen (`OPTIONAL_CONTAINER_VARS` en `edge/src/index.ts`).
Si se cambia `BRIAN_TELEGRAM_SECRETO`, hay que volver a registrar el webhook (Brian → Telegram →
*Registrar webhook*). Las rutas `/brian/mcp` y `/brian/telegram/*` pasan por el Worker sin caché; un
POST a `www.` se redirige con 308 (conserva el cuerpo), pero conviene usar siempre el dominio
canónico. Cómo conectar clientes MCP y el bot: `docs/BRIAN.md` → *Conectarse*.

### Pimienta del PIN de los socios (`DCASA_PIN_PEPPER`) y clave de cifrado de respaldos (`PGBACKREST_CIPHER_PASS`)

Las dos se generan **una vez** y **no se cambian nunca**: cambiar la pimienta rompe el PIN de
**todos** los socios a la vez; cambiar la clave de cifrado deja ilegibles los respaldos ya guardados y
corta el archivado del WAL. Cloudflare no deja leer un secreto guardado, así que **la copia del
dueño es el único respaldo**:

1. Generarlas: `openssl rand -hex 32` (una para cada una, y distintas por entorno).
2. Guardarlas en el gestor de contraseñas del dueño (fuera de Cloudflare y de GitHub).
3. Cargarlas en el environment de GitHub.

El despliegue las sube al Worker **solo si el Worker todavía no las tiene** (cada entorno es otro
Worker: `dcasa` y `dcasa-staging`). Para saberlo consulta la
API de Cloudflare: si la consulta falla (token, red, 5xx) o la respuesta no es la esperada, **aborta
sin escribir nada** (S-03); solo un 404 (Worker nuevo) o un listado válido sin el secreto permiten
subirla. Ya no se genera una pimienta al azar sin copia: si falta en GitHub, el despliegue no avanza.

Recuperarlas tras perder el Worker: `cd edge && npx wrangler secret put DCASA_PIN_PEPPER --env=""`
(y `PGBACKREST_CIPHER_PASS`; para staging `--env=staging`) pegando la copia del gestor de contraseñas.

## 4. Primer despliegue

Primero **staging** (pasos para el dueño en `docs/OPERACION.md` → «Primer despliegue a staging»):
*Actions → CI/CD → Run workflow*, rama `main`, `desplegar_en = staging`. El primer arranque, con el
bucket vacío, crea la base (instala los módulos en español) y empieza a archivar en R2: tarda unos
minutos. Luego `<URL_SITIO>/web/login` con `admin` / `ODOO_ADMIN_PASSWORD`.

Producción: con la receta de arriba («La receta de producción»). El primer despliegue a producción fue el 2026-10-13
(CI #117). Un merge a `main` no despliega por sí solo.
Después, crear un usuario por persona y no compartir el de administrador.

## 5. Actualizaciones de módulos en el arranque (I-02) y cómo volver atrás

Cada despliegue lleva un `APP_VERSION` nuevo (el SHA). Al arrancar, el contenedor nuevo compara esa
versión con la guardada en la base y, si cambió, corre `odoo -u` de los módulos de D'CASA **antes** de
abrir el puerto. Esa actualización modifica la base en el sitio y no se deshace sola. Por eso:

- **Antes de cada despliegue** a un entorno que ya existe, el pipeline pide un respaldo por
  `POST /__edge/respaldo` (`dcasa-respaldo`: `pg_dump` cifrado a R2 y, según la imagen, un respaldo
  base de pgBackRest) y **no despliega si falla**. El resumen de la ejecución anota la hora: ese es el
  punto al que volver. Además, el WAL continuo permite volver a cualquier segundo anterior al despliegue.
  *Pendiente con `f1-imagen`*: que `dcasa-respaldo` incluya un `pgbackrest backup --type=full` cuando
  `DCASA_RESPALDO_ORIGEN=manual`, para que la vuelta atrás no dependa de reproducir todo el WAL.
- **Solo hay una instancia** (`max_instances = 1`) y no se despliega en paralelo
  (`concurrency: desplegar-<entorno>`): nunca corren dos `-u` a la vez sobre la misma base.
- **Cambios de versión de módulos** (`version` en un `__manifest__.py`, scripts de migración en
  `migrations/`, actualización de `vendor/odoo`): primero a **staging** con una copia reciente, revisar,
  y recién después merge a `main`. Desplegar a producción fuera del horario de venta.

**Volver atrás** (detalle paso a paso en `docs/OPERACION.md` → «Volver atrás un despliegue»):

1. **Restaurar la base** al punto previo: el respaldo completo previo del despliegue malo (o un
   instante anterior al despliegue, con restauración a un punto en el tiempo).
2. **Desplegar la imagen anterior**: *Actions → Desplegar → Run workflow* con `entorno`, el
   `imagen_digest` y el `app_version` que figuran en el resumen del despliegue **bueno** anterior,
   y `respaldo_previo` desmarcado si el sitio está caído. No se reconstruye nada: se usa la imagen que
   ya está en el registro. Como la base restaurada tiene la versión vieja, no corre ningún `-u`.

Nunca desplegar la imagen vieja sobre la base ya actualizada sin restaurar: Odoo con módulos más
viejos que la base puede romper vistas y datos.

### Qué hace cada arranque del contenedor (`docker/entrypoint.sh`)

> Fase 1: antes de estos pasos la imagen arranca su PostgreSQL local y, si R2 tiene respaldos,
> restaura la base (pgBackRest) y la promueve; si la restauración falla, sale con error y nunca
> crea una base vacía encima (`edge/CONTRATO_CONTENEDOR.md` §1). El detalle de esa parte lo
> documenta la imagen (`docker/`).

1. **Espera a PostgreSQL** (`DB_REINTENTOS`, por defecto 20 intentos cada 3 s). Si no
   responde, el contenedor **falla**: nunca confunde «no pude consultar» con «base nueva»
   (antes un error de conexión disparaba una instalación y un reseteo de clave).
2. **Instala** (base nueva) o **actualiza** (otra `APP_VERSION`) los módulos de D'CASA.
3. **Sanea el usuario `admin`** en cada arranque hasta que quede el marcador
   `dcasa.admin_saneado` en la base: si `admin` sigue con la clave `admin` (o vacía), la
   cambia por `ADMIN_PASSWORD` **antes** de abrir el puerto. Si el contenedor muere entre la
   instalación y este paso, el siguiente arranque lo repite. Si el dueño ya cambió la
   clave de `admin`, no se toca.
4. **Desinstala los módulos sobrantes** (una vez por versión, marcador
   `dcasa.sobrantes_version`): SMS (`sms`, `*_sms`), correo postal (`snailmail*`),
   IAP y autocompletar (`iap*`, `crm_iap_*`, `iap_crm`, `partner_autocomplete`), UBL europeo
   (`account_edi_ubl_cii`, `purchase_edi_ubl_bis3`, `sale_edi_ubl`), tableros de hoja de
   cálculo (`spreadsheet_dashboard*`, `spreadsheet_account`), lista de deseos y comparador
   (`website_sale_wishlist`, `website_sale_comparison*`) y `base_import_module`. Se quedan
   `crm`, `sale_crm`, `calendar`, `auth_totp*`, `base_import` y todos los `dcasa_*`.
   Los puentes automáticos que dependen de un sobrante (p. ej.
   `website_sale_stock_wishlist`) se van con él; si algo instalado a propósito lo requiere,
   el sobrante se queda y se registra en el log. Un fallo no impide arrancar: se reintenta en el
   siguiente arranque. Se repite en cada versión porque instalar un módulo nuevo puede volver
   a instalar los `auto_install` (p. ej. `account_edi_ubl_cii`). Para desactivarlo:
   `ODOO_DESINSTALAR_SOBRANTES=0`.
5. Arranca Odoo.

La **contraseña maestra** (`admin_passwd`) es distinta de la de `admin`: viene de
`ODOO_MASTER_PASSWORD` o, si falta (o es igual a la de `admin`), se genera aleatoria y no se
imprime. El gestor de bases no hace falta: `list_db = False` y el borde bloquea
`/web/database/*`.

## 6. Dominio `dcasapty.com`

**Hecho.** `dcasapty.com` y `www.dcasapty.com` apuntan al Worker `dcasa` desde el 2026-10-27 (Desplegar 31): `routes`
con `custom_domain` en `edge/wrangler.jsonc` (Cloudflare crea solo los registros DNS y los certificados; el borde manda
`www` → `dcasapty.com`), `workers_dev: true` para que `workers.dev` siga respondiendo (ahí viven el webhook de Brian y lo
que Juan ya conoce) y `routes: []` en staging (si no, heredaría el dominio). `URL_SITIO` de `production` es
`https://dcasapty.com`. Cómo se hizo, paso a paso: [historico/TRASLADO_DOMINIO.md](historico/TRASLADO_DOMINIO.md);
lo que salió mal (Desplegar 29 y 30) y por qué: [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md) › Despliegue.

> Los QR impresos del programa de socios deben apuntar a `https://dcasapty.com/socios`
> (o `/r/CÓDIGO`), nunca a `*.workers.dev`: un QR impreso es permanente.

**Regla que dejó el traslado:** un cambio del borde (`routes`, `vars`, `workers_dev`) se despliega con un `app_version`
que lo contenga: *Desplegar* hace checkout de ese commit, no de `main`.

## Rutas bloqueadas en el borde

El Worker responde 404 (sin llegar a Odoo) a `/web/database/*`, `/jsonrpc`, `/xmlrpc*`,
`/json/2*` y `/doc-bearer*` (`BLOCKED_PREFIXES` en `edge/src/routing.ts`). La comparación
se hace sobre la ruta **normalizada**: decodifica `%XX` (también doble codificación como
`%2564`), colapsa `//`, resuelve `.`/`..`, pasa `\` a `/` y a minúsculas, y también quita
un prefijo de idioma (`/es/jsonrpc` llega a `/jsonrpc` en Odoo, incluso por POST).

- `/jsonrpc` y `/xmlrpc*` despachan el servicio `db` (`drop`, `dump`, `restore`,
  `change_admin_password`), protegido solo por la contraseña maestra. El borde no inspecciona
  el cuerpo, así que se bloquean completos: nada de D'CASA los usa (el sitio y el backend
  usan `/web/dataset/*`; Brian, `/brian/mcp`).
- `/json/2` (API externa de Odoo 19 con clave de API) queda **bloqueada por ahora**
  (recomendación de la ronda 3, `docs/auditoria/ronda3/brian-agente.md`). Cuando Brian en el
  borde la necesite, se abrirá con su propia protección (p. ej. solo desde el Worker o con
  Cloudflare Access), no desde internet abierto.

## Conexiones a PostgreSQL

Odoo corre con `workers = 0` (un proceso con hilos): todas las peticiones simultáneas y el
hilo de cron comparten un solo pool de `db_maxconn` conexiones. Con 16 se midió ~75 % de
respuestas 500 (`PoolError: The Connection Pool Is Full`) con 20-50 peticiones a la vez
(`docs/auditoria/ronda3/odoo-medicion.md`); con 64 no hubo errores. El valor por defecto es
ahora **48** (`ODOO_DB_MAXCONN`), suficiente para ~45 peticiones simultáneas; el límite real
es la CPU (~13 pet./s en un proceso con hilos), no las conexiones.

Regla: `db_maxconn` + conexiones de mantenimiento (respaldos, `psql`, el arranque) +
`superuser_reserved_connections` (3) ≤ `max_connections` de PostgreSQL.

- PostgreSQL dentro del mismo contenedor (Fase 1): `max_connections = 64` alcanza
  (48 de Odoo + 3 reservadas + margen para pgBackRest/`pg_dump`). Cada conexión activa
  cuesta memoria de PostgreSQL (medido: ~430 MiB de PostgreSQL con ~50 conexiones bajo
  carga), así que no conviene subir ambos números sin medir en el contenedor (producción `standard-1`, 4 GiB; staging
  `basic`, 1 GiB).
- Si algún día se sube `db_maxconn`, subir `max_connections` en la misma proporción.

## Sesiones y salud de Odoo (`dcasa_sesiones`)

- **Las sesiones viven en la base**, no en el disco: el módulo `dcasa_sesiones` guarda las sesiones
  HTTP de Odoo en la tabla `dcasa_http_session` (llave = SHA-256 del identificador). Como la base se
  restaura desde R2, **las sesiones sobreviven a reinicios y despliegues**: vendedoras, carritos y
  socios siguen conectados (salvo lo escrito en el último minuto antes de una caída brusca). Se carga
  como módulo de todo el servidor (`server_wide_modules = base,web,dcasa_sesiones`, en
  `ODOO_MODULES` de la imagen); en CI, `odoo-tests` lo carga igual vía `ODOO_RC`. La limpieza la hace
  el autovacuum diario de Odoo (7 días de inactividad por defecto).
- **`GET /dcasa/salud`** es la salud de Odoo: 200 `{"ok": true}` si Odoo y la base responden, 503 si
  no; sin sesión ni cookie. La consulta el Worker (timeout 5 s, sin despertar el contenedor) para
  responder **`GET /__edge/health`**, que es lo que miran el despliegue y el dueño
  (`docs/OPERACION.md` → «Si el sitio se cae»). En la imagen de producción además trae `version` (12
  primeros del commit de la imagen que responde) y `base_al_dia` (la base se actualizó con el código de
  esa imagen). El despliegue (`.github/scripts/esperar_salud.sh`) exige `version` = `app_version` y
  `base_al_dia` = true, y vigila 600 s antes de confirmar; un 200 de otra imagen no cuenta (incidente 1 de
  CONTEXTO_AGENTICO).
- **Cuándo se actualiza la base.** La imagen guarda su commit (`/opt/dcasa/COMMIT`, del CI) y la huella de
  su código (`/opt/dcasa/CODIGO`). El arranque actualiza los módulos si la huella no coincide con
  `dcasa.codigo_desplegado` de la base o si la versión cambió; la versión que manda es la de la imagen,
  no la variable `APP_VERSION` (Cloudflare puede arrancar la imagen nueva con las variables del arranque
  anterior: así quedó la base sin actualizar el 2026-10-16).

## Cron del Worker

`edge/wrangler.jsonc` define dos disparos (UTC), iguales en producción y staging
(`runScheduled` en `edge/src/handler.ts`, con test):

- **`7 * * * *`, cada hora**: si el contenedor está apagado lo enciende; si está encendido no hace
  nada (Odoo corre sus acciones planificadas con su propio hilo, `max_cron_threads = 1`). Es la red de
  seguridad del 24/7.
- **`17 8 * * *`, 03:17 de Panamá**: respaldo lógico diario dentro del contenedor
  (`/usr/local/bin/dcasa-respaldo`). Si Odoo está apagado no lo enciende para respaldar: lo
  confirmado ya está en el WAL de R2.

Producción queda **encendida 24/7** (`ODOO_DORMIR_TRAS` vacío): dormir implica restaurar la base desde
R2 al despertar. En `edge/wrangler.jsonc` staging también tiene `ODOO_DORMIR_TRAS` vacío (24/7); con `"1h"` se
dormiría tras una hora sin visitas. Aun así, el despliegue a staging del CI lo ha encontrado apagado varias veces
(CONTEXTO_AGENTICO › Despliegue).

## Operación

Todo lo del día a día está en **[docs/OPERACION.md](OPERACION.md)**: costos, simulacros mensuales,
qué hacer si el sitio cae, restaurar a un punto en el tiempo, volver atrás un despliegue y dónde ver
los logs.

- **Actualizar Odoo** (parches de seguridad de la 19.0):
  `git -C vendor/odoo fetch --depth 1 origin 19.0 && git -C vendor/odoo checkout FETCH_HEAD`,
  correr `make test`, commit, **probar en staging** y luego merge a `main` (§5).
- **Alternativa sin Containers**: cualquier VPS con `docker compose --profile tunnel up -d`
  y un *Cloudflare Tunnel* (`CLOUDFLARE_TUNNEL_TOKEN`); misma imagen.
