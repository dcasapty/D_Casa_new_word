# Contrato Worker ↔ contenedor de Odoo (Fase 1)

Qué espera el borde (`edge/`) de la imagen (`docker/`, `scripts/`) y qué le da. Fase 1,
opción A: Odoo + PostgreSQL en **un** contenedor `basic`, instancia única, 24/7 en
producción, que restaura la base desde R2 al arrancar. Fuente de verdad del código:
`src/index.ts` (Durable Object `OdooContainer`) y `src/handler.ts` (lógica con tests).

## 1. Lo que la imagen debe cumplir

| # | Requisito | Por qué |
|---|---|---|
| 1 | Odoo escucha en **8069** y **no abre el puerto hasta que la base está restaurada y promovida**. | El borde considera «listo» el contenedor en cuanto el puerto responde HTTP (`pingEndpoint = localhost/web/health`; cualquier código vale). Si abriera antes, las visitas llegarían a un Odoo sin base. |
| 2 | Arranque completo (restauración desde R2 + Odoo) en **≤ 420 s** (la instalación inicial midió 263 s; una restauración normal ~10 s). | Tope `TOPE_ARRANQUE_MS`. Pasado eso el borde lo da por fallido, lo registra y no reintenta durante 30 s. Mientras tanto las visitas reciben 503 con `Retry-After: 15`. |
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
| Parada (rollout, reinicio de host, salida del proceso) | `onStop` registra `exitCode` y motivo; en 24/7 programa un rearranque a los 30 s, como mucho uno cada 10 min (evita restaurar desde R2 en bucle). El cron horario es la red de seguridad (solo en 24/7: con `ODOO_DORMIR_TRAS` de duración, staging, no despierta al contenedor). |

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
| `DCASA_STOCK_PRUEBA` | var | — | `0` · staging `10`. Unidades de prueba para cada producto inventariable sin existencias **ni movimientos** (`dcasa_catalogo.stock_prueba`, `aplicar_stock_prueba`; nunca pisa un conteo real). Solo vale con `DCASA_ENTORNO=staging`: en producción el entrypoint la deja **siempre en 0** |
| `DCASA_BLACK_WEEKEND` | var | — | `0` · staging `1`. `1` = Black Weekend visible sin mirar fechas (vista previa); `0` = solo dentro de la ventana (`dcasa_black_weekend.activo`, addons/website_dcasa/models/black_weekend.py) |
| `DCASA_BLACK_WEEKEND_INICIO` / `_FIN` | var | — | `2026-10-02` / `2026-10-11` (AAAA-MM-DD, hora de Panamá, inclusivas). Vacías: el entrypoint no toca lo que haya en Odoo. El cron horario de `dcasa_tienda_borde` regenera la tienda cuando la campaña empieza o termina |
| `DCASA_ADJUNTOS` | var | — | `r2` (por defecto) · `db`. Dónde guarda Odoo los adjuntos **nuevos** (`addons/dcasa_adjuntos_r2`). Con `r2` usa las mismas `R2_*`, prefijo `adjuntos/` del bucket; con `db` sigue leyendo los que ya están en R2 y un cron los trae de vuelta a la base (emergencia) |
| `CANONICAL_HOST` | var | — | `dcasapty.com` · `staging.dcasapty.com` |
| `APP_VERSION` | var | — | por defecto `dev` |
| `DCASA_PIN_PEPPER` | secreto | — | nunca se rota |
| `ODOO_MASTER_PASSWORD` | secreto | — | opcional |
| `BRIAN_*`, `TELEGRAM_BOT_TOKEN` | var/secreto | — | opcionales |
| `TIENDA_FEED_TOKEN` | secreto | — | ≥ 32 caracteres. Odoo lo exige en `GET /dcasa/tienda/feed` (cabecera `X-Dcasa-Tienda-Token`) y lo manda como `Bearer` al avisar `POST /__edge/tienda/regenerar` (§5) |
| `TIENDA_AVISO_URL` | var | — | opcional; por defecto `https://<CANONICAL_HOST>/__edge/tienda/regenerar` |
| `DCASA_2FA_OBLIGATORIO` | var | — | `0` (por defecto). `1` = quien está en el alcance enrola la app de códigos al entrar (addons/dcasa_seguridad). Encender solo cuando la dueña ya enroló la suya (docs/SEGURIDAD_ACCESO.md) |
| `DCASA_2FA_ALCANCE` | var | — | `admins` (por defecto) o `internos` |
| `DCASA_SESION_ADMIN_HORAS` / `DCASA_INACTIVIDAD_ADMIN_MIN` | var | — | opcionales (al instalar: 12 h / 60 min; `0` = sin). Vacías: no se toca lo que haya en Odoo |
| `DCASA_AVISO_LOGIN_TELEGRAM` | var | — | `0` apaga el aviso por Telegram de inicios de sesión de administrador |
| `DCASA_ROBOTS_IA` | var | — | `abierta` · `equilibrada` (por defecto) · `cerrada`: política de robots.txt para rastreadores de IA |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET` | var / secreto | — | opcionales, las dos juntas: Cloudflare Turnstile en login, registro, cambio de clave, formularios y /socios. `DCASA_TURNSTILE=off` lo apaga (rescate) |

Adjuntos en R2: el entrypoint copia `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY` (y `R2_REGION`, `R2_VERIFY_TLS`) a `DCASA_ADJUNTOS_R2_*` para el proceso de
Odoo, que guarda el contenido de `ir.attachment` en `adjuntos/<sha1[:2]>/<sha1>` del mismo bucket.
Un respaldo de la base **sin** ese prefijo no restaura los archivos (`docs/OPERACION.md`).

Solo del Worker (no entran al contenedor): `RESPALDO_TOKEN` (≥ 32 caracteres, p. ej.
`openssl rand -hex 32`), `ODOO_DORMIR_TRAS`, `TIENDA_ESTATICA` y el binding KV `TIENDA` (§5).

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

## 5. Tienda estática (Fase 2 v1)

Sitio público rápido generado desde los datos de Odoo; la tienda real (carrito, pago, apartado y
abonos cuando haya pasarela, portal `/my`) sigue en Odoo. Código: `edge/src/tienda/` (generador y
almacén), `edge/src/routing.ts` (`rutaEstatica`), `addons/dcasa_tienda_borde` (feed, marcas, «Agregar»).

```
Odoo (cambio de precio/stock/venta/factura) ──marca──▶ dcasa.tienda.pendiente
   └─ ir.cron (disparado al confirmar, +20 s) ──POST /__edge/tienda/regenerar (Bearer)──▶ Worker
Worker ──GET /dcasa/tienda/feed (X-Dcasa-Tienda-Token, directo al contenedor)──▶ Odoo
Worker: renderizarSitio(feed) → escribe en KV solo las páginas cuyo ETag cambió (manifiesto)
Visitante: GET /, /shop, /shop/page/N, /shop/category/<slug>[/page/N], /shop/<slug>, /visitanos,
           /privacidad, /terminos, /black-weekend ──▶ KV (si TIENDA_ESTATICA=on); si no está ──▶ Odoo, como antes
```

| Pieza | Contrato |
|---|---|
| `GET /dcasa/tienda/feed` | Solo con `TIENDA_FEED_TOKEN` (si falta o no coincide: 404). Bloqueada en el borde desde internet; el Worker la pide al contenedor. Usuario público del sitio: solo lo publicado. JSON `version: 1` (`edge/src/tienda/tipos.ts`). |
| `POST /__edge/tienda/regenerar` | `Authorization: Bearer <TIENDA_FEED_TOKEN>`. 200 con el resumen; 503 si el feed falla (Odoo reintenta); 404 sin token/KV. Un feed vacío no borra un sitio publicado. |
| `POST /dcasa/carrito/agregar-borde` | Formulario sin JS (`product_template_id`, o `product_id` de la variante). `csrf=False` + **mismo origen** (`Origin` = sitio; si no hay, `Sec-Fetch-Site: same-origin`; si no, `Referer`). La cookie de sesión de Odoo es `SameSite=Lax`. Redirige a `/shop/cart`. |
| Black Weekend | El feed trae `black_weekend` (opcional; `activo` ya evaluado en hora de Panamá, productos con precio de la tienda y combo). Sin `activo` (o sin productos) no hay banda, ni etiqueta, ni `/black-weekend` (la página se borra de KV y Odoo responde 404). El cron horario de Odoo (`cron_vigilar_black_weekend`) avisa al Worker cuando la campaña empieza o termina. |
| Cron horario del Worker | Si Odoo ya está encendido, regenera todo (red de seguridad). No lo despierta. |
| `TIENDA_ESTATICA` | `on` sirve desde KV; `off` (producción por ahora) todo a Odoo. La regeneración funciona igual, para tener KV listo antes de encender. |
| `DCASA_ENTORNO=staging` | `X-Robots-Tag: noindex, nofollow` en **todas** las respuestas del Worker. |

**Qué se sirve estático y qué no.** Solo `GET/HEAD` de esas rutas y sin parámetros (salvo `utm_*`,
`gclid`, `fbclid`…): búsqueda, filtros y orden van a Odoo. Fichas cuyo modo de compra es `ficha`
(atributos dinámicos o sin variante, valores a medida, combos, opcionales) no se generan: las sirve
Odoo con su configurador. Las variantes simples (hasta 30) se eligen con botones de radio sin JS.
Las páginas estáticas son iguales para todos (sin contador de carrito ni nombre del cliente); un
cliente con sesión las ve igual y su carrito, `/my` y el pago siguen en Odoo.

**Almacén: Workers KV (decidido).** KV está hecho para lecturas globales de valores chicos con caché
en cada centro de datos (`cacheTtl` 60 s), sin servidor en medio; las páginas pesan 15-60 KB. Costo
en Workers Paid: 10 M lecturas y 1 M escrituras/mes incluidas (luego $0,50/M y $5/M;
https://developers.cloudflare.com/workers/platform/pricing/, consultado 2026-10-02): una
regeneración completa son ~210 escrituras y las incrementales solo las páginas que cambiaron
(manifiesto con ETag), así que el uso esperado cabe en lo incluido (≈ $0). Se descartó **Workers
Static Assets** (gratis, pero cada cambio exigiría un `wrangler deploy` desde CI: minutos y una
versión nueva por cambio de stock) y **R2** (lecturas desde una sola región, sin caché por centro de
datos sin agregar Cache API; útil si algún día hay miles de páginas o archivos grandes).
Consistencia: KV es eventual (hasta ~60 s en otros centros de datos) + `cacheTtl` 60 s ⇒ un cambio
se ve en ≤ ~2 min en el peor caso.

**Imágenes.** Las fotos de producto salen de `GET /dcasa/img/<modelo>/<id>/<campo>/<ancho>.<webp|jpg>?v=<v>`
(`addons/website_dcasa/models/imagen.py` y `controllers/imagen.py`), no de `/web/image`: Odoo 19 sirve
cada foto en el formato en que se subió (sin WebP para quien lo acepta) y, si el original es WebP, no
lo achica. Contrato:

| Pieza | Regla |
|---|---|
| Modelos | `product.template`/`image_1920`, `product.product`/`image_variant_1920` (solo si la variante tiene foto propia; si no, la URL es la de la plantilla), `product.image`/`image_1920`. Otro par: 404. |
| Ancho y formato | `256`, `512`, `1024`, `1600` × `webp` (calidad 80) o `jpg` (progresivo, 82). Se parte de la foto más grande guardada y **nunca se agranda**; sin metadatos. |
| Versión `v` | `checksum[:12]` del adjunto de la foto: cambia solo si cambia la foto. Sin `v` o con una vieja: `302` a la vigente (`no-cache`). |
| Respuesta | `200`, `Cache-Control: public, max-age=31536000, immutable`, `ETag` (304 si coincide), sin `Set-Cookie` (`save_session=False`). El borde la guarda (`CACHEABLE_PATTERNS`, exige `?v=`). |
| Visibilidad | Solo si la plantilla está publicada en el sitio (`_dcasa_dominio_publicado`) y la variante activa; si no, `404 no-store`. |
| Generación | Una vez por (foto, ancho, formato): queda en `dcasa.imagen.variante` (adjunto ⇒ R2 con `dcasa_adjuntos_r2`). Al cambiar la foto se borran las de la versión vieja (el objeto de R2 lo recoge el cron de 45 días). Si Pillow no puede (SVG), `302` a `/web/image`. |
| Feed | `imagen.foto = {base, v}` y `galeria_fotos[]` (además de las URL de `/web/image`, de respaldo), `sitio.imagen_anchos`. |
| Páginas | Estáticas (`edge/src/tienda/render.ts`) y tarjetas de Odoo (`/shop`, carriles de la portada): `<picture>` con `<source type="image/webp" srcset=…>` + `<img>` JPEG/Odoo con `width/height`, `sizes`; perezosas salvo la LCP (`eager` + `fetchpriority="high"`, y `preload` WebP en la ficha). |

Por qué en Odoo y no en Cloudflare: el **Images binding** del Worker trabaja con bytes, no con URL de zona (en
`workers.dev`: NO VERIFICADO) y daría AVIF, pero cobra por transformación única (5 000/mes gratis en el plan Free de
Images; luego hay que pasar a Images Paid, $0,50/1 000 —https://developers.cloudflare.com/images/pricing/,
consultado 2026-10-02) y en `workers.dev` la caché del Worker no está garantizada (ronda4/rendimiento.md):
cada visita volvería a bajar la foto de 1920 px del contenedor. Las transformaciones por URL
(`/cdn-cgi/image`) exigen una zona propia con transformaciones activas: hoy no la hay. Con ~250 productos
× 3 anchos × 2 formatos (~1 500 variantes) generar en Odoo una sola vez y guardarlas en R2 cuesta $0 y
no depende del dominio. La imagen de producción (Ubuntu 24.04, Python 3.12 ⇒ Pillow 10.2.0 en rueda)
tiene WebP pero no AVIF (llega con Pillow 11.2+): AVIF queda para cuando haya dominio (binding o
transformaciones de zona) si el LCP lo pide.

Medido (2026-10-02, 120 fotos reales de `dcasa_catalogo`, mismo `image_1920`): mediana por foto Odoo
JPEG → WebP: 256 px 10,0 → 4,4 KB; 512 px 33,6 → 13,4 KB; 1024 px 108,4 → 35,5 KB (total −39 %, −45 %,
−60 %). El JPEG de respaldo pesa como el de Odoo (±8 %). Lighthouse móvil sobre `/shop` de Odoo con 24
productos de fotos reales (local, sin Brotli; 3 corridas): imágenes 440 → 197 KB (11 peticiones, el logo
de 57 KB incluido); el LCP de laboratorio no cambia (~24 s: lo marca el JS/CSS de Odoo sin comprimir).
Generar una variante: ~0,2 s de un núcleo la primera vez; luego se sirve guardada (~30 ms).

**Medición de laboratorio (2026-10-02).** Feed real de una base con `dcasa_catalogo` (188 productos:
172 de compra directa, 16 con variantes; feed 352 KB, 0,59 s en Odoo local), 212 páginas generadas
(HTML mediana 14,8 KB, máx. 59,7 KB sin comprimir); servidor local con Brotli y fotos/fuentes por
proxy a Odoo. Lighthouse 12 móvil, 3 corridas, mediana: portada **100** (LCP 1,81 s, 458 KB, 13
peticiones), `/shop` **99** (LCP 1,85 s), ficha **100** (LCP 1,91 s, 240 KB), Visítanos **99** (LCP
1,87 s); TBT 0 ms y CLS ≤ 0,001 en todas; accesibilidad, buenas prácticas y SEO 100. Solo laboratorio:
sin red Panamá↔borde ni datos de campo.

**Fuera de esta v1:** reseñas e «Inspírate» de la portada, buscador estático, contador del carrito
en la cabecera estática, JSON de existencias por producto con caché corta (hoy la disponibilidad
solo se publica si `PUBLICAR_DISPONIBILIDAD` de `website_dcasa` es verdadero, y se refresca por
regeneración), `sitemap.xml` propio (sigue el de Odoo: mismas URL), y redirigir/`noindex` el `/shop`
de Odoo cuando el estático esté encendido.
