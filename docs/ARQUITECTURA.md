# Arquitectura

```
                    ┌──────────────────────── Cloudflare ────────────────────────┐
 Cliente / tienda   │                                                            │
 ─────────────────► │  Worker "dcasa" (edge/src)                                 │
 dcasapty.com       │   · bloquea /web/database (gestor de bases)                │
                    │   · www → dominio canónico                                 │
                    │   · caché de assets e imágenes públicas                    │
                    │   · cabeceras de seguridad y X-Forwarded-*                 │
                    │   · cron cada 10 min → despierta Odoo (acciones planif.)   │
                    │            │                                               │
                    │            ▼                                               │
                    │  Durable Object "OdooContainer" ──► Container (standard-2) │
                    │                                    docker/Dockerfile       │
                    │                                    Odoo 19 + addons/       │
                    └────────────────────────────────────────────┬───────────────┘
                                                                 │ TLS (sslmode=require)
                                                                 ▼
                                                  PostgreSQL gestionado (Neon)
                                                  datos + adjuntos (imágenes, PDF)
```

## Piezas

**Worker** (`edge/src/index.ts`): punto de entrada público. Toda la lógica de
decisiones está en `routing.ts`/`handler.ts` (probada con vitest sin Cloudflare).

**Container**: la imagen `docker/Dockerfile` (Ubuntu 24.04, Python 3.12,
wkhtmltopdf para los PDF, solo traducciones en español). Odoo corre en modo
multihilo en el puerto 8069 (HTTP + websocket en un solo puerto, que es lo que
expone el contenedor). Una sola instancia (`max_instances: 1`).

**Arranque** (`docker/entrypoint.sh`):
- genera `odoo.conf` desde variables de entorno (sin secretos en la imagen);
- base vacía → instala `dcasa_base, dcasa_invoice, dcasa_socios, website_dcasa` en español;
- base existente y versión de imagen distinta (`APP_VERSION` = commit) → actualiza
  esos módulos una sola vez; reinicios normales no actualizan (arranque ~10 s).

**Base de datos**: PostgreSQL gestionado. Usar la conexión **directa** (no la del
*pooler* en modo transacción): Odoo usa `LISTEN/NOTIFY` para el bus en tiempo real.

## Por qué así

- El disco del contenedor es **efímero** → los adjuntos (imágenes de productos,
  PDF) se guardan en la base (`ir_attachment.location = db`, lo fija `dcasa_base`).
  Efecto secundario aceptable: al reiniciarse el contenedor se cierran las sesiones.
- La **pimienta del PIN** de los socios (`DCASA_PIN_PEPPER`) es un secreto del Worker que
  se pasa al contenedor; vive fuera de la base, así un volcado robado no permite atacar los PIN.
- El contenedor **duerme** tras 30 min sin tráfico; el cron del Worker lo despierta
  cada 10 min para que corran las acciones planificadas de Odoo.
- Nada de datos de negocio vive en Cloudflare fuera de la base: se puede mover a
  otro proveedor (VPS + `cloudflared`, ver `docker-compose.yml`, perfil `tunnel`) sin
  cambiar código.

## Módulos

```
dcasa_base ──► dcasa_invoice ──► dcasa_socios ──► website_dcasa
```

| Módulo | Depende de (Odoo) | Tests |
|---|---|---|
| `dcasa_base` | contacts, crm, sale_management, sale_stock, purchase, stock, account, l10n_pa | 10 |
| `dcasa_invoice` | account, sale | 7 |
| `dcasa_socios` | sale_management, account, website_sale | 79 |
| `website_dcasa` | website_sale | 11 |
