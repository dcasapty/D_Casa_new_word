# Despliegue en Cloudflare

El despliegue es automático: cada push a `main` que pasa todos los tests se
publica con `wrangler deploy` (Worker + imagen del contenedor). Esto se configura
**una sola vez**.

## 1. Base de datos PostgreSQL

Cloudflare no ofrece PostgreSQL propio; se usa uno gestionado. Recomendado: **Neon**
(plan con respaldos y restauración a un punto en el tiempo).

1. Crear proyecto en región `us-east` (la más cercana a Panamá).
2. Crear base `dcasa` y usuario `dcasa`.
3. Copiar el **host de conexión directa** (no el `-pooler`): Odoo necesita `LISTEN/NOTIFY`.

## 2. Cloudflare

1. Cuenta de Cloudflare con plan **Workers Paid** (necesario para Containers).
2. Crear un **API Token** con permisos *Workers Scripts: Edit*, *Workers Routes: Edit*,
   *Containers: Edit* y *Account Settings: Read*.
3. Anotar el **Account ID**.

## 3. GitHub (Settings → Secrets and variables → Actions)

Crear el *environment* `production` y cargar:

| Tipo | Nombre | Valor |
|---|---|---|
| Secret | `CLOUDFLARE_API_TOKEN` | token del paso 2 |
| Secret | `CLOUDFLARE_ACCOUNT_ID` | account id |
| Secret | `DB_PASSWORD` | contraseña del usuario `dcasa` en Neon |
| Secret | `ODOO_ADMIN_PASSWORD` | clave del usuario `admin` de Odoo (larga y aleatoria) |
| Secret | `ODOO_MASTER_PASSWORD` | opcional: contraseña maestra de Odoo (`admin_passwd`), **distinta** de la anterior. Si falta, el contenedor genera una aleatoria en cada arranque y no la muestra (el gestor de bases está cerrado igual) |
| Secret | `DCASA_PIN_PEPPER` | opcional pero recomendado: la pimienta del PIN generada por el dueño y guardada en su gestor de contraseñas (ver más abajo) |
| Variable | `DB_HOST` | host directo de Neon, p. ej. `ep-xxx.us-east-2.aws.neon.tech` |
| Variable | `DB_USER` | `dcasa` |
| Variable | `DB_NAME` | `dcasa` |
| Variable | `CANONICAL_HOST` | `dcasapty.com` |

### Brian, el asistente (opcional)

Sin estas variables Brian queda instalado pero sin IA ni Telegram (el chat lo avisa). Todas
se cargan en el environment `production` de GitHub; **nunca en el repositorio** ni en
`wrangler.jsonc`. El despliegue sube los secretos con `wrangler secret bulk` y el Worker los
pasa al contenedor de Odoo solo si existen (`OPTIONAL_CONTAINER_VARS` en `edge/src/index.ts`).

| Tipo | Nombre | Valor |
|---|---|---|
| Variable | `BRIAN_PROVEEDOR` | `anthropic`, `openai`, `xai`, `groq`, `openrouter` u `ollama` |
| Variable | `BRIAN_MODELO` | opcional con Anthropic (por defecto `claude-sonnet-5-5`) |
| Variable | `BRIAN_BASE_URL` | solo para proveedores OpenAI-compatibles propios |
| Secret | `BRIAN_API_KEY` | clave del proveedor de IA |
| Secret | `TELEGRAM_BOT_TOKEN` | token del bot (@BotFather) |
| Secret | `BRIAN_TELEGRAM_SECRETO` | `openssl rand -hex 32`: ruta y encabezado del webhook de Telegram |

A mano, sin GitHub: `cd edge && npx wrangler secret put TELEGRAM_BOT_TOKEN` (y así cada uno).
Si se cambia `BRIAN_TELEGRAM_SECRETO`, hay que volver a registrar el webhook (Brian →
Telegram → *Registrar webhook*). Las rutas `/brian/mcp` y `/brian/telegram/*` pasan por el
Worker sin caché; un POST a `www.` se redirige con 308 (conserva el cuerpo), pero conviene
usar siempre el dominio canónico. Cómo conectar clientes MCP y el bot: `docs/BRIAN.md` →
*Conectarse*.

### Pimienta del PIN de los socios (`DCASA_PIN_PEPPER`)

Cambiarla rompe el PIN de **todos** los socios a la vez y no tiene vuelta atrás.
Cloudflare no deja leer un secreto una vez guardado, así que **hay que respaldarla fuera
de Cloudflare** antes del primer despliegue:

1. Generarla una vez: `openssl rand -hex 32`.
2. Guardarla en el gestor de contraseñas del dueño (fuera de Cloudflare y de GitHub;
   si se pierde la cuenta de Cloudflare, ese es el único respaldo).
3. Cargarla en el environment `production` de GitHub como secreto `DCASA_PIN_PEPPER`.

El despliegue la sube al Worker **solo si el Worker todavía no tiene una**; si ya existe,
no la toca nunca. Si no hay secreto en GitHub, la genera al azar (como antes) y deja un
aviso: esa pimienta **no tiene copia** en ningún lado.

El paso es seguro ante fallos (S-03): primero lista los secretos del Worker y, si
`wrangler secret list` falla (token sin permiso, red, error 5xx) o devuelve algo que no
es la lista esperada, **aborta el job sin escribir nada**. Solo crea la pimienta tras un
listado exitoso que no la contiene. Si el job falla en ese paso, basta con reintentarlo.

Recuperarla tras perder el Worker: `cd edge && npx wrangler secret put DCASA_PIN_PEPPER`
y pegar la copia del gestor de contraseñas.

Sin los secretos de Cloudflare, el job de despliegue se salta con un aviso (los
tests igual corren).

## 4. Primer despliegue

Push a `main` (o *Run workflow*). El primer arranque del contenedor crea toda la
base (instala los módulos en español): tarda unos minutos. Para no hacerlo
esperar en la primera visita, se puede inicializar antes desde una máquina con Docker:

```bash
docker build -f docker/Dockerfile -t dcasa-odoo .
docker run --rm -e DB_HOST=<neon> -e DB_USER=dcasa -e DB_PASSWORD=<...> \
  -e DB_NAME=dcasa -e DB_SSLMODE=require -e ADMIN_PASSWORD=<clave de admin> \
  -e APP_VERSION=init dcasa-odoo --stop-after-init
```

Luego entrar en `https://dcasa.<cuenta>.workers.dev/web/login` con usuario `admin` y
la contraseña `ODOO_ADMIN_PASSWORD`. Después, crear un usuario por persona y no
compartir el de administrador.

### Qué hace cada arranque del contenedor (`docker/entrypoint.sh`)

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

## 5. Dominio `dcasapty.com`

> Los QR impresos del programa de socios deben apuntar a `https://dcasapty.com/socios`
> (o `/r/CÓDIGO`), nunca a `*.workers.dev`: un QR impreso es permanente.


1. Agregar el dominio a Cloudflare y cambiar los *nameservers* en el registrador.
2. En `edge/wrangler.jsonc` descomentar `routes` (dcasapty.com y www) y hacer push.
3. En Odoo: Ajustes → Parámetros del sistema → `web.base.url` = `https://dcasapty.com`.

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

- Hoy (Neon): revisar el máximo de conexiones del plan; 48 debe caber.
- Fase 1 (PostgreSQL dentro del mismo contenedor): `max_connections = 64` alcanza
  (48 de Odoo + 3 reservadas + margen para pgBackRest/`pg_dump`). Cada conexión activa
  cuesta memoria de PostgreSQL (medido: ~430 MiB de PostgreSQL con ~50 conexiones bajo
  carga), así que no conviene subir ambos números sin medir en el contenedor basic (1 GiB).
- Si algún día se sube `db_maxconn`, subir `max_connections` en la misma proporción.

## Cron del Worker

`edge/wrangler.jsonc` dispara `scheduled()` **cada hora** (minuto 7). Antes era `*/10`, que
hacía `fetch` al contenedor cada 10 minutos y, con `sleepAfter = "30m"`, impedía que
durmiera nunca (720 h/mes forzadas; `docs/auditoria/ronda3/cf-plataforma.md` §4.4).

Ahora (`runScheduled` en `edge/src/handler.ts`):

- Si el contenedor **está encendido**, no hace nada: Odoo corre sus acciones planificadas
  con su propio hilo de cron (`max_cron_threads = 1`) y el Worker no le renueva el
  temporizador de inactividad.
- Si **está apagado**, lo despierta una vez para que Odoo ponga al día lo pendiente
  (cola de correo, cron horario de socios: vencer canjes y regalos de cumpleaños); luego
  vuelve a dormir tras `sleepAfter` si nadie lo usa.

En la arquitectura A (Odoo + PostgreSQL en el mismo contenedor, Fase 1) el contenedor va a
estar encendido 24/7 por decisión de operación (dormir implica restaurar la base): eso se
configurará con `sleepAfter`/política del contenedor en la Fase 1, no con un cron que lo
golpee cada 10 minutos.

## Operación

- **Logs**: panel de Cloudflare → Workers → `dcasa` → Logs (incluye los del contenedor).
- **Actualizar Odoo** (parches de seguridad de la 19.0):
  `git -C vendor/odoo fetch --depth 1 origin 19.0 && git -C vendor/odoo checkout FETCH_HEAD`,
  correr `make test`, commit y push. El contenedor actualiza los módulos solo.
- **Respaldos**: PITR de Neon (restaurar a cualquier minuto) + copia manual con
  `pg_dump` antes de cambios grandes.
- **Alternativa sin Containers**: cualquier VPS con `docker compose --profile tunnel up -d`
  y un *Cloudflare Tunnel* (`CLOUDFLARE_TUNNEL_TOKEN`); mismo código, misma imagen.
