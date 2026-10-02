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

## 5. Caché de páginas (HTML de Odoo en el borde)

Una sola fuente de diseño: el borde **no dibuja nada**. Guarda, byte a byte, la página que Odoo
dibuja para un visitante anónimo y se la sirve a los anónimos; quien tiene sesión propia pasa directo
a Odoo. Reemplaza a la «tienda estática» (plantilla propia del Worker alimentada por un feed), que se
borró el 2026-10-02 porque no tenía el navbar, el héroe ni el footer del sitio. Código:
`edge/src/tienda/paginas.ts`, `edge/src/routing.ts` (`rutaEstatica`), `addons/dcasa_tienda_borde`.

```
Visitante GET /, /shop, /shop/page/N, /shop/category/<slug>[/page/N], /shop/<slug>, /visitanos,
          /privacidad, /terminos, /black-weekend (sin parámetros salvo utm_*, gclid, fbclid…)
  ├─ con cookie dcasa_personal o Authorization ──────────────▶ Odoo (X-Dcasa-Cache: BYPASS)
  └─ anónimo ─▶ KV html:<host><ruta>
        ├─ válida (t ≥ invalidado) y < 1 h ──────────────────▶ HIT (Odoo ni se entera)
        ├─ válida y ≥ 1 h ─▶ STALE: se sirve y se pide otra a Odoo en segundo plano
        └─ no está o es anterior a la invalidación ─▶ MISS: Odoo (sin cookies, X-Dcasa-Borde: <token>)
              └─ 200 + «X-Dcasa-Borde: anonimo» + sin Set-Cookie ─▶ se guarda y se sirve; si no, Odoo
Odoo (precio, stock, venta, factura, categoría, ajustes, plantilla, menú, página, tarifa, Black Weekend)
  ──marca──▶ dcasa.tienda.pendiente ──cron (+20 s)──POST /__edge/tienda/regenerar (Bearer)──▶ Worker
Worker: KV invalidado = ahora (1 escritura) y, ya respondido, pide a Odoo /, /shop, /black-weekend y
        las fichas que cambiaron (`rutas`, ≤ 30)
```

| Pieza | Contrato |
|---|---|
| Cookie `dcasa_personal` | La pone Odoo (`models/ir_http.py`, `_post_dispatch`) a quien tiene en la sesión usuario (`uid`, `pre_uid`) o cualquier dato fuera de `CLAVES_NEUTRAS` (carrito, `website_sale_cart_quantity`, `wishlist_ids`, socio, tarifa elegida, modo lista…). La quita cuando ya no (cerró sesión, pagó, expiró). `session_id` NO sirve: Odoo se la pone a todo anónimo. HttpOnly, SameSite=Lax. |
| Relleno | El Worker pide la página SIN cookies, sin IP del visitante, con `User-Agent` fijo, `X-Disable-Tracking: 1` y `X-Dcasa-Borde: <TIENDA_FEED_TOKEN>`. Con ese secreto Odoo no guarda sesión ni manda `Set-Cookie` y, si la dibujó para el usuario público sin nada propio, responde `X-Dcasa-Borde: anonimo`. Sin esa marca, con `Set-Cookie`, no-200 o no-HTML: no se guarda (al visitante le llega la respuesta de Odoo a SU petición). El visitante no puede mandar `X-Dcasa-Borde` (el borde la quita). |
| CSRF | Lo único que cambia entre dos dibujos anónimos. La página guardada lleva el de la sesión del relleno; `static/src/js/borde_csrf.js` (en `web.assets_frontend`) pide `GET /dcasa/borde/csrf` (no-store, guarda la sesión) al tocar un formulario y detiene el envío POST hasta tenerlo. Solo actúa si la navegación trae `Server-Timing: dcasa-borde`. JSON-RPC (carrito de la ficha) no usa CSRF. |
| Respuesta al visitante | HTML tal cual + `Content-Type` de Odoo, `Cache-Control: no-cache`, `ETag` (304 desde el borde), `Server-Timing: dcasa-borde;desc="HIT"`, `X-Dcasa-Cache: HIT/MISS/STALE/BYPASS`, cabeceras de seguridad y, en staging, `X-Robots-Tag: noindex, nofollow`. Nunca `Set-Cookie`. |
| Nunca se guarda | `/web*`, `/my*`, `/shop/cart*`, `/shop/checkout`, pago, `/socios`, `/brian`, `/dcasa/*`, búsqueda/filtros/orden (`?search`, `?order`, `?attribute_values`…), POST y todo lo que no esté en la lista de rutas. |
| `POST /__edge/tienda/regenerar` | `Authorization: Bearer <TIENDA_FEED_TOKEN>`. 200 `{estado, invalidado, precalentar}`; 503 si KV no escribe (Odoo reintenta cada 15 min); 404 sin token (≥ 32) o sin KV. Funciona con la caché apagada. |
| Claves de KV | `html:<host><ruta>` (valor = HTML; metadatos `{t, etag, ct}`; `expirationTtl` 7 días) e `invalidado` (ms). Una página vale si `t ≥ invalidado`: invalidar es UNA escritura, sin listar ni borrar. `<host>` en la clave: workers.dev y el dominio no se mezclan (canonical, og:url). |
| `TIENDA_ESTATICA` | `on` = caché de páginas encendida (staging); `off` = todo a Odoo (producción hasta que la dueña lo apruebe). Sin `TIENDA_FEED_TOKEN` válido la caché no existe aunque diga `on`. |
| KV caído | Lectura que falla → la página la sirve Odoo, como si la caché no existiera. Escritura que falla → solo se registra (`pagina_escritura_fallida`). |

**Almacén: Workers KV, no Cache API (decidido).** Cache API (`caches.default`) es gratis y ~1 ms, pero
es por centro de datos (cada uno llena su copia pidiéndosela a Odoo), purgar en todos exige la API de
purga de la zona y en `workers.dev` (staging hoy, sin dominio propio) no guarda nada. KV es global: un
solo relleno sirve a todos los centros de datos, la invalidación es una escritura y funciona en
`workers.dev`. Costo (Workers Paid: 10 M lecturas y 1 M escrituras/mes incluidas; luego $0,50/M y
$5/M, https://developers.cloudflare.com/workers/platform/pricing/, consultado 2026-10-02): cada vista
anónima = 2 lecturas (`invalidado` + página; con `cacheTtl` 30 s en el centro de datos); cada página
se escribe como mucho una vez por hora de tráfico (STALE) y una vez por invalidación (~35 precalentadas
+ las que se visiten). Con ~200 páginas y unas decenas de cambios al día queda dentro de lo incluido
(≈ $0). Consistencia: una invalidación tarda ≤ ~1-2 min en verse en otros centros de datos (KV
eventual + `cacheTtl`); en el que la escribió (y precalentó), al instante. Medido local: precio
cambiado en Odoo → el borde sirve el nuevo a los 24 s (20 s de `PAUSA_AVISO` + cron).

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
| Páginas | Tarjetas de Odoo (`/shop`, carriles de la portada; las mismas que guarda la caché de páginas): `<picture>` con `<source type="image/webp" srcset=…>` + `<img>` JPEG/Odoo con `width/height`, `sizes`; perezosas salvo la LCP (`eager` + `fetchpriority="high"`, y `preload` WebP en la ficha). |

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

**Medición (2026-10-02, local).** Base con `dcasa_catalogo`, Odoo local (`workers=0`) detrás del
mismo `handleRequest` en `wrangler dev` (KV de miniflare). HTML del borde = HTML de Odoo byte a byte
salvo el token CSRF en `/`, `/shop`, una ficha y `/black-weekend`; capturas (escritorio 1280 y móvil
390) iguales (las de escritorio de `/` y `/shop` solo con antialiasing distinto: ningún píxel difiere
más de 40/255). Chromium móvil, mediana de 5: TTFB Odoo → borde (HIT): `/` 37 → 17 ms (la portada ya
la cachea Odoo), `/shop` 187 → 13 ms, ficha 131 → 12 ms, `/black-weekend` 127 → 15 ms; LCP 328 → 304,
480 → 340, 424 → 360, 388 → 340 ms. Solo laboratorio (sin red, CPU local mucho más rápida que el
contenedor `basic` de 1/4 vCPU): en producción la ganancia de TTFB debería ser mayor.

**Pendiente:** contador del carrito y menú de usuario en páginas guardadas no hacen falta (quien los
tiene pasa a Odoo); las visitas servidas desde la caché no llegan a «Visitantes» de Odoo (el
rastreo de productos vistos sigue por JS); un usuario que ya estaba logueado antes de desplegar esto
ve UNA página anónima hasta su primera respuesta de Odoo (que le pone la cookie).
