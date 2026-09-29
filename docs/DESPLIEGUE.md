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
| Secret | `ODOO_ADMIN_PASSWORD` | contraseña maestra de Odoo (larga y aleatoria) |
| Variable | `DB_HOST` | host directo de Neon, p. ej. `ep-xxx.us-east-2.aws.neon.tech` |
| Variable | `DB_USER` | `dcasa` |
| Variable | `DB_NAME` | `dcasa` |
| Variable | `CANONICAL_HOST` | `dcasapty.com` |

Sin los secretos de Cloudflare, el job de despliegue se salta con un aviso (los
tests igual corren).

## 4. Primer despliegue

Push a `main` (o *Run workflow*). El primer arranque del contenedor crea toda la
base (instala los módulos en español): tarda unos minutos. Para no hacerlo
esperar en la primera visita, se puede inicializar antes desde una máquina con Docker:

```bash
docker build -f docker/Dockerfile -t dcasa-odoo .
docker run --rm -e DB_HOST=<neon> -e DB_USER=dcasa -e DB_PASSWORD=<...> \
  -e DB_NAME=dcasa -e DB_SSLMODE=require -e ADMIN_PASSWORD=<...> \
  -e APP_VERSION=init dcasa-odoo --stop-after-init
```

Luego entrar en `https://dcasa.<cuenta>.workers.dev/web/login` con usuario `admin` y
la contraseña `ODOO_ADMIN_PASSWORD` (el arranque nunca deja `admin`/`admin` en una
base nueva; se puede usar otra con la variable `ADMIN_USER_PASSWORD`). Después,
crear un usuario por persona y no compartir el de administrador.

## 5. Dominio `dcasapty.com`

1. Agregar el dominio a Cloudflare y cambiar los *nameservers* en el registrador.
2. En `edge/wrangler.jsonc` descomentar `routes` (dcasapty.com y www) y hacer push.
3. En Odoo: Ajustes → Parámetros del sistema → `web.base.url` = `https://dcasapty.com`.

## Operación

- **Logs**: panel de Cloudflare → Workers → `dcasa` → Logs (incluye los del contenedor).
- **Actualizar Odoo** (parches de seguridad de la 19.0):
  `git -C vendor/odoo fetch --depth 1 origin 19.0 && git -C vendor/odoo checkout FETCH_HEAD`,
  correr `make test`, commit y push. El contenedor actualiza los módulos solo.
- **Respaldos**: PITR de Neon (restaurar a cualquier minuto) + copia manual con
  `pg_dump` antes de cambios grandes.
- **Alternativa sin Containers**: cualquier VPS con `docker compose --profile tunnel up -d`
  y un *Cloudflare Tunnel* (`CLOUDFLARE_TUNNEL_TOKEN`); mismo código, misma imagen.
