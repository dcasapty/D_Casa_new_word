# Contrato Worker ↔ contenedor de Odoo (Fase 1)

Qué espera el borde (`edge/`) de la imagen (`docker/`, `scripts/`) y qué le da. Fase 1,
opción A: Odoo + PostgreSQL en **un** contenedor `basic`, instancia única, 24/7 en
producción, que restaura la base desde R2 al arrancar. Fuente de verdad del código:
`src/index.ts` (Durable Object `OdooContainer`) y `src/handler.ts` (lógica con tests).

## 1. Lo que la imagen debe cumplir

| # | Requisito | Por qué |
|---|---|---|
| 1 | Odoo escucha en **8069** y **no abre el puerto hasta que la base está restaurada y promovida**. | El borde considera «listo» el contenedor en cuanto el puerto responde HTTP (`pingEndpoint = localhost/web/health`; cualquier código vale). Si abriera antes, las visitas llegarían a un Odoo sin base. |
| 2 | Arranque completo (restauración desde R2 + Odoo) en **≤ 180 s**. | Tope `TOPE_ARRANQUE_MS`. Pasado eso el borde lo da por fallido, lo registra y no reintenta durante 30 s. Mientras tanto las visitas reciben 503 con `Retry-After: 15`. |
| 3 | Si falta algo crítico (credenciales de R2, clave de cifrado) o la restauración falla, **salir con código ≠ 0**; nunca crear una base vacía cuando R2 tiene respaldos. | `onStop` registra `exitCode` y motivo. El borde ya no enciende el contenedor si faltan secretos (ver §3). |
| 4 | Manejar **SIGTERM**: parar Odoo → `CHECKPOINT` → `pg_switch_wal()` → esperar el archivado → `pg_ctl stop -m fast` → salir. Hay hasta 15 min antes del SIGKILL. | Cloudflare manda SIGTERM en cada rollout (despliegue), reinicio de host y, en staging, al dormir. |
| 5 | Ruta **`GET /dcasa/salud`** (la pone `f1-sesiones` en `addons/`): `2xx` si Odoo y la base responden; otro código si no. Cuerpo corto (JSON), sin datos sensibles; responde en < 5 s. | `/__edge/health` la consulta con timeout de 5 s, solo si el contenedor ya está `healthy` (nunca lo despierta). |
| 6 | Ejecutable **`/usr/local/bin/dcasa-respaldo`** (copia de `scripts/respaldo.sh`, `chmod +x`). | Lo lanza el cron diario y `POST /__edge/respaldo` (§2). |

### Respaldo diario: `dcasa-respaldo`

- Lo ejecuta el Durable Object con **`ctx.container.exec()`** (mecanismo oficial de
  Containers para correr procesos dentro de un contenedor en marcha), no por HTTP: no hay
  puerto ni token expuesto dentro del contenedor.
- Comando exacto: `timeout --kill-after=30 840 /usr/local/bin/dcasa-respaldo`
  (sin shell; la imagen necesita `timeout` de coreutils). Máximo 14 min.
- Usuario: el de la imagen (`USER odoo`). Directorio: el `WORKDIR` de la imagen.
- Entorno: **el mismo que recibe el contenedor** (lista del §3, se pasa explícito a
  `exec()`), más `DCASA_RESPALDO_ORIGEN=cron|manual`.
- Qué hace (decisión de `f1-imagen`): como mínimo `pg_dump -Fc` cifrado al bucket
  `R2_BUCKET` en un prefijo propio del respaldo lógico, distinto del repositorio de
  pgBackRest. Puede además lanzar un respaldo base de pgBackRest.
- Debe ser **idempotente y con candado** (`flock`): el borde evita dos ejecuciones a la vez
  dentro de la misma instancia, pero el script no debe confiar solo en eso.
- Salida: código **0 = éxito**; cualquier otro = fallo. stdout y stderr se combinan y el
  borde guarda los **últimos 2 000 caracteres** en Workers Logs: **nunca imprimir
  secretos** (ni URLs con credenciales). Última línea recomendada: un resumen
  (`respaldo ok: dcasa-2026-10-01.dump 12.3 MB en 41 s`).
- Si Odoo no está encendido, el borde **no** lo enciende para respaldar (devuelve
  `omitido`): todo lo confirmado ya está en el WAL archivado.

## 2. Lo que el borde hace

| Cuándo | Qué |
|---|---|
| Visita y Odoo listo | Reenvía (con las cabeceras de proxy y seguridad de la Fase 0). |
| Visita y Odoo apagado/arrancando | Dispara (o reutiliza) un único arranque, espera hasta 8 s y, si no está, responde **503** con `Retry-After: 15`, `Cache-Control: no-store` y una página que se recarga sola (texto plano para POST/Brian/Telegram). |
| Faltan secretos para arrancar | **No** enciende el contenedor; 503 con `Retry-After: 60` y error en el log (`arranque_bloqueado`). |
| `GET /__edge/health` | JSON `{borde, odoo, contenedor, salud_http?, detalle?, faltan?}`. **200** solo si `/dcasa/salud` dio 2xx; si no, **503** (`odoo`: `arrancando`, `detenido`, `error`, `sin_configurar`). No despierta el contenedor. |
| `POST /__edge/respaldo` + `Authorization: Bearer <RESPALDO_TOKEN>` | Respaldo a mano (simulacros). 200 ok · 500 fallo · 409 en curso · 503 Odoo apagado · 401 token malo · 404 si `RESPALDO_TOKEN` no está o tiene < 32 caracteres. Responde al terminar (hasta 14 min). |
| Otras `/__edge/*` | 404; nunca llegan a Odoo. |
| Cron `7 * * * *` (cada hora) | Si el contenedor está apagado, lo enciende; si está encendido no hace nada. |
| Cron `17 8 * * *` (03:17 Panamá) | Respaldo diario (§1). |
| Inactividad (`ODOO_DORMIR_TRAS`) | Vacío = **24/7**: el temporizador se revisa pero nunca apaga. En staging `1h`: SIGTERM tras 1 h sin visitas. |
| Parada (rollout, reinicio de host, salida del proceso) | `onStop` registra `exitCode` y motivo; en 24/7 programa un rearranque a los 30 s, como mucho uno cada 10 min (evita restaurar desde R2 en bucle). El cron horario es la red de seguridad. |

Eventos en Workers Logs (JSON): `arranque_iniciado`, `arranque_listo`, `arranque_fallido`,
`arranque_bloqueado`, `contenedor_detenido`, `contenedor_error`, `respaldo`,
`reenvio_fallido`.

## 3. Variables y secretos que recibe el contenedor

Se pasan solo si están definidas (`variablesDelContenedor`). **Ya no se pasa `DB_HOST` ni
nada de Neon**: PostgreSQL es local y su configuración (socket/127.0.0.1, usuario, clave
interna) la decide la imagen. Si la imagen quiere nombre de base configurable, usa su
propio valor por defecto (`dcasa`).

| Nombre | Tipo | Obligatoria para arrancar | Notas |
|---|---|---|---|
| `ADMIN_PASSWORD` | secreto | sí | clave de `admin` de Odoo |
| `R2_ENDPOINT` | secreto | sí | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | secreto | sí | token de R2 limitado a **un** bucket |
| `PGBACKREST_CIPHER_PASS` | secreto | sí | cifrado del repositorio; perderla = perder los respaldos |
| `R2_BUCKET` | var | sí | `dcasa-respaldos` · staging `dcasa-respaldos-staging` |
| `DCASA_ENTORNO` | var | — | `produccion` · `staging` (por defecto `produccion`) |
| `CANONICAL_HOST` | var | — | `dcasapty.com` · `staging.dcasapty.com` |
| `APP_VERSION` | var | — | por defecto `dev` |
| `DCASA_PIN_PEPPER` | secreto | — | nunca se rota |
| `ODOO_MASTER_PASSWORD` | secreto | — | opcional |
| `BRIAN_*`, `TELEGRAM_BOT_TOKEN` | var/secreto | — | opcionales |

Solo del Worker (no entran al contenedor): `RESPALDO_TOKEN` (≥ 32 caracteres, p. ej.
`openssl rand -hex 32`), `ODOO_DORMIR_TRAS`.

## 4. Política de scheduling: `default` (decidido ahora)

La política es **inmutable** («To use a different policy, create a new Container
application»; https://developers.cloudflare.com/containers/configuration/scheduling-policy/,
2026-09-30). Se eligió `default` porque la `durable_object` (beta pública desde 2026-09-30):

- **rechaza** `instance_type`, `max_instances` y `constraints`
  (https://developers.cloudflare.com/workers/wrangler/configuration/): sin `max_instances: 1`
  ni `regions: ["ENAM"]` la unicidad y la cercanía a Panamá quedarían solo en el código;
- **no admite la clase `Container`** de `@cloudflare/containers`
  (https://developers.cloudflare.com/containers/api/container-class/): habría que reescribir
  arranque, espera de puertos, proxy y sueño sobre `ctx.container`;
- su única ventaja aquí, los **snapshots**, no compensa con una base de 100-200 MB
  (`docs/auditoria/ronda3/datos.md` §3: «el snapshot no compensa su complejidad aquí»).

Migrar después es posible y barato **porque el Durable Object no guarda datos** (la base
vive en R2): se crea otra clase (p. ej. `OdooContainerDO`) con `scheduling_policy:
"durable_object"`, se migra el código a `ctx.container.start({ image, instance: "basic" })`
y se corta el tráfico. Guía: /containers/guides/migrate-to-durable-object-scheduling-policy/.
Requisito para ese corte: el **candado en R2** de la imagen, para que la app vieja y la
nueva nunca escriban a la vez en el mismo repositorio.

Rollouts con `max_instances: 1`: un solo paso al 100 %; la instancia vieja recibe SIGTERM,
sale, y recién entonces arranca la nueva (https://developers.cloudflare.com/containers/configuration/rollouts/).
Durante ese hueco las visitas ven el 503 amable.
