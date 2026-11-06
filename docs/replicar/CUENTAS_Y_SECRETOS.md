# Cuentas, secretos y variables

Parte de [Cómo instalar este sistema para otra empresa](../REPLICAR.md) (§2, §5 y §6). Qué cuentas crear y **cada**
secreto y variable que el sistema lee, por **nombre**, con el lugar donde va y de dónde sale. Verificado el
**2026-11-06** contra `.github/workflows/*.yml`, `.github/scripts/`, los tres `wrangler.jsonc`, `edge/src/index.ts`,
`edge/src/handler.ts` y `juan/src/env.ts`.

> **Ningún valor va aquí, ni en el repositorio, ni en un chat.** Quien instala dice *dónde* se pega cada secreto y
> comprueba que quedó cargado sin ver su valor (GitHub y Cloudflare muestran el nombre, nunca el contenido).

## 1. Las cuentas

| Cuenta | Para qué | ¿Obligatoria? | De dónde sale el dato | Notas |
|---|---|---|---|---|
| **Cloudflare** con el plan **Workers Paid** | Workers, Containers (solo existen en el plan de pago), Durable Objects, KV | Sí | [OPERACION.md › Plan de Cloudflare](../OPERACION.md) | La cuenta es la llave maestra: 2FA y códigos de recuperación impresos ([SEGURIDAD_ACCESO.md §4](../SEGURIDAD_ACCESO.md)) |
| **R2** en esa cuenta | Respaldos de la base y adjuntos: dos buckets, uno por entorno | Sí | [OPERACION.md › Crear los buckets de R2](../OPERACION.md) | Ubicación ENAM, sin acceso público |
| **Workers AI** (viene con la cuenta) | Juan: notas de voz, lectura de imágenes y búsqueda por significado | Solo con Juan y `TRANSCRIBIR_AUDIO` / `RECONOCER_IMAGENES` en `"1"` | `juan/wrangler.jsonc:21-24,52-55` | Se factura a la cuenta de Cloudflare |
| **Cloudflare Zero Trust** (plan Free) | La puerta del equipo (`/master`) con PIN al correo | No, pero recomendado | [SEGURIDAD_ACCESO.md §8.4](../SEGURIDAD_ACCESO.md) | Gratis hasta 50 personas; puede pedir tarjeta |
| **Dominio** con DNS en Cloudflare | Dirección definitiva; hasta entonces, `workers.dev` | No al principio | [DESPLIEGUE.md §6](../DESPLIEGUE.md), [TRASLADO_DOMINIO.md](../TRASLADO_DOMINIO.md) | Los QR impresos van siempre al dominio, nunca a `workers.dev` |
| **GitHub** con Actions | Pruebas, imagen y despliegues; environments `staging` y `production` | Sí | §2 | 2FA y códigos de recuperación impresos. Cada imagen guardada como artefacto pesa ~420 MB y dura 1 día ([OPERACION.md](../OPERACION.md)) |
| **Proveedor de IA para Brian** (Anthropic, OpenAI, xAI, Groq, OpenRouter u Ollama) | Brian, el asistente del panel | **Sí**: el despliegue exige `BRIAN_API_KEY` | [BRIAN.md › Configuración](../BRIAN.md) | En staging, una clave de pruebas con tope de gasto |
| **Proveedor de IA para Juan** (Anthropic, Meta u OpenAI) | Que Juan conteste | Solo si se usa Juan | [JUAN_WORKER.md §8](../JUAN_WORKER.md) | Se elige en Odoo; solo hace falta la clave del elegido (y la del respaldo) |
| **Meta Business** (portafolio verificado), **app de Meta** y **WhatsApp Cloud API** | Juan por WhatsApp (API oficial), Messenger e Instagram | Solo si se usa ese canal | [JUAN_PLAN_B.md](../JUAN_PLAN_B.md), [JUAN_META.md](../JUAN_META.md) | La verificación del negocio tarda días: empezarla pronto |
| **Meta: píxel y Conversions API** | Medir anuncios | No (todo apagado de fábrica) | [META_EVENTOS.md](../META_EVENTOS.md), [META_CATALOGO.md](../META_CATALOGO.md) | Exige la sección de Meta en la política de privacidad, aprobada por la asesoría legal |
| **Telegram** (@BotFather): **dos** bots | Uno para Brian (panel, alertas, avisos de Sofía) y otro para Juan (canal de pruebas) | No | [BRIAN.md › Telegram](../BRIAN.md), [JUAN_WORKER.md §6](../JUAN_WORKER.md) | Un bot tiene un solo destino: no se comparten |
| **Resend** | Correo a clientes | No (apagado de fábrica) | [CORREO.md](../CORREO.md) | Una clave «solo envío» por entorno y el dominio verificado |
| **Cloudflare Turnstile** | Captcha invisible | No (apagado) | [SEGURIDAD_ACCESO.md §6.2](../SEGURIDAD_ACCESO.md) | — |
| **Gestor de contraseñas** de la gerencia | Guardar las claves que no se rotan nunca (§7) | **Sí** | — | Antes del primer despliegue |

## 2. GitHub

### 2.1 Environments

*Settings › Environments*: crear **`staging`** y **`production`**. En `production`, *Deployment branches and tags* →
*Selected branches* → solo `main` ([DESPLIEGUE.md §3](../DESPLIEGUE.md)). En un repositorio **público** GitHub ofrece
además *Required reviewers*; en uno privado de los planes Free, Pro o Team no existe, y la aprobación es el clic de
quien lanza el despliegue (`.github/workflows/desplegar.yml:74-76`). Producción nunca se engancha a un push: lo vigila
`edge/test/despliegue-produccion.test.ts`.

Cada environment lleva **sus propios** valores: staging nunca comparte bucket, token, clave de cifrado ni pimienta con
producción.

### 2.2 Secretos y variables de cada environment

Los lee `.github/workflows/desplegar.yml`; los de `desplegar-juan.yml` y `desplegar-puente.yml` son solo los dos
primeros. Las líneas son de `desplegar.yml`.

| Tipo | Nombre | ¿Obligatorio? | Para qué | Cómo se genera | Línea |
|---|---|---|---|---|---|
| Secreto | `CLOUDFLARE_API_TOKEN` | Sí | Desplegar (también Juan y el puente) | Token de cuenta con los permisos de [REPLICAR.md §5](../REPLICAR.md) | 92 |
| Secreto | `CLOUDFLARE_ACCOUNT_ID` | Sí | La cuenta; arma `R2_ENDPOINT` y la dirección del registro de imágenes | Página principal de *Workers & Pages* | 93 |
| Variable | `URL_SITIO` | Sí | Dirección pública del Worker `dcasa` de ese entorno, `https://…` sin `/` final. Su anfitrión se vuelve `CANONICAL_HOST` si esta queda vacía (`:286-296`) | `https://dcasa.<subdominio>.workers.dev` (staging: `https://dcasa-staging.<subdominio>.workers.dev`) hasta tener dominio | 79, 94 |
| Secreto | `R2_ACCESS_KEY_ID` | Sí | Respaldos y adjuntos | Token de R2 limitado al bucket de ese entorno | 99, 136 |
| Secreto | `R2_SECRET_ACCESS_KEY` | Sí | Ídem | Ídem (se muestra una sola vez) | 137 |
| Secreto | **`PGBACKREST_CIPHER_PASS`** | Sí (≥ 32) | Cifra los respaldos. Perderla = respaldos ilegibles. **Nunca se rota**; se sube al Worker solo si todavía no la tiene | `openssl rand -hex 32` | 138, 253 |
| Secreto | `RESPALDO_TOKEN` | Sí (≥ 32) | Autoriza `POST /__edge/respaldo` (respaldo previo y a mano) | `openssl rand -hex 32` | 139 |
| Secreto | `ODOO_ADMIN_PASSWORD` | Sí | Clave inicial del usuario `admin` (en el Worker se llama `ADMIN_PASSWORD`) | Gestor de contraseñas, larga y al azar | 140 |
| Secreto | `ODOO_MASTER_PASSWORD` | Sí | Contraseña maestra de Odoo, **distinta** de la anterior | Gestor de contraseñas | 141 |
| Secreto | **`DCASA_PIN_PEPPER`** | Sí (≥ 32) | Pimienta del PIN de los socios. **Nunca se rota** (cambiarla invalida el PIN de todos); se sube solo si el Worker no la tiene | `openssl rand -hex 32` | 142, 252 |
| Secreto | `BRIAN_API_KEY` | Sí | IA de Brian | Panel del proveedor | 143 |
| Secreto | `TELEGRAM_BOT_TOKEN` | No | Bot de Brian; también las alertas del Worker y de Odoo | @BotFather | 237 |
| Secreto | `BRIAN_TELEGRAM_SECRETO` | No | Ruta y cabecera del webhook de Brian (solo `A-Z a-z 0-9 _ -`) | `openssl rand -hex 32` | 238 |
| Secreto | `RESEND_API_KEY` | No | Correo a clientes; sin ella no sale ninguno | Resend, permiso «solo envío», una por entorno | 240 |
| Secreto | `META_CAPI_TOKEN` | No | Ventas hacia la Conversions API de Meta | Administrador de eventos de Meta ([META_EVENTOS.md](../META_EVENTOS.md)) | 242 |
| Secreto | `TIENDA_FEED_TOKEN` | No (sí para la caché de páginas) | Odoo y el Worker se reconocen para la caché | `openssl rand -hex 32`, distinto por entorno | 244 |
| Secreto | `TURNSTILE_SECRET` | No | Turnstile (con la variable `TURNSTILE_SITE_KEY`, §3) | Panel de Turnstile | 246 |
| Secreto | `DCASA_PUERTA_RUTA` | No (las cuatro juntas) | Ruta de la puerta del equipo (p. ej. `/master`) | La misma ruta de la aplicación de Access | 248 |
| Secreto | `DCASA_PUERTA_SECRETO` | No (las cuatro juntas) | Firma la cookie y las cabeceras de la puerta | `openssl rand -hex 32`, distinto por entorno | 249 |
| Secreto | `DCASA_ACCESS_EQUIPO` | No (las cuatro juntas) | Equipo de Zero Trust | `https://<equipo>.cloudflareaccess.com` | 250 |
| Secreto | `DCASA_ACCESS_AUD` | No (las cuatro juntas) | La aplicación de Access | Su *Application Audience (AUD) Tag* | 251 |
| Variable | `CANONICAL_HOST` | No | Pisa el de `edge/wrangler.jsonc`. **Vacía** = el anfitrión de `URL_SITIO` (lo correcto) | — | 280 |
| Variable | `R2_ENDPOINT` | No | Solo si el bucket está en otra jurisdicción; por defecto `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` (`.github/scripts/secretos_despliegue.sh:81`) | — | 230 |
| Variables | `BRIAN_PROVEEDOR`, `BRIAN_MODELO`, `BRIAN_BASE_URL` | No | Proveedor y modelo de Brian ([BRIAN.md › Configuración](../BRIAN.md)) | — | 281-283 |

**Qué valida el despliegue antes de tocar Cloudflare** (`.github/scripts/validar_entorno.sh`, llamado en
`desplegar.yml:147-150`): que los obligatorios existan y no estén vacíos; que no tengan marcadores (`CAMBIAR`,
`PENDIENTE`, `REEMPLAZAR`, `CHANGEME`, `PLACEHOLDER`, `<...>`) ni saltos de línea; ≥ 32 caracteres en
`PGBACKREST_CIPHER_PASS`, `RESPALDO_TOKEN` y `DCASA_PIN_PEPPER`; `URL_SITIO` con `https://` y sin `/` final; maestra
distinta de la de `admin`. Si un environment no tiene **ninguno** de los secretos de despliegue, el despliegue se
omite con un aviso (`desplegar.yml:96-109`).

**Qué sube cada despliegue al Worker** (`.github/scripts/secretos_despliegue.sh:85-109`): todos los de la tabla que
tengan valor (los vacíos no se suben); `DCASA_PIN_PEPPER` y `PGBACKREST_CIPHER_PASS` solo si el Worker todavía no los
tiene (`:70-78`). Si la consulta de secretos a Cloudflare falla, aborta sin escribir nada (`:57-61`).

### 2.3 Secretos del repositorio (no de un environment), opcionales

| Nombre | Lo usa | Para qué |
|---|---|---|
| `PREVIEW_ADMIN_PASSWORD` | `.github/workflows/preview.yml:85` | Clave del `admin` de la previsualización |
| `BRIAN_API_KEY_PRUEBAS` | `.github/workflows/preview.yml:86` | Brian en la previsualización (si falta, usa `BRIAN_API_KEY`) |
| `UP_MEDIA_TOKEN` | `.github/workflows/up-media.yml:75` | Solo si `main` tiene una protección que el `GITHUB_TOKEN` no puede saltar (*up media* hace commit a `main`) |

## 3. Panel de Cloudflare: Worker `dcasa` / `dcasa-staging`

Se pegan en *Workers & Pages › `dcasa` (o `dcasa-staging`) › Settings › Variables and Secrets* **después** de que el
Worker exista. Los despliegues usan `--keep-vars` (`.github/workflows/desplegar.yml:304-306`) y no los borran. Lo que
cambia en el panel llega al contenedor **al reiniciar o en el siguiente despliegue** (la lista de lo que viaja es
`VARIABLES_DEL_CONTENEDOR`, `edge/src/handler.ts:510-593`).

| Nombre | Tipo | Para qué |
|---|---|---|
| `JUAN_ODOO_TOKEN` | Secreto | Juan se identifica ante Odoo. **Mismo valor** que en `dcasa-juan` (§6). Sin él, `/dcasa/juan/**` responde 503 |
| `JUAN_WORKER_TOKEN` | Secreto | Odoo se identifica ante Juan. **Mismo valor** que en `dcasa-juan` |
| `JUAN_URL` | Variable | Dirección del Worker de Juan (`https://dcasa-juan.<subdominio>.workers.dev`) para que Odoo lo llame. También se puede poner en Odoo, *Ajustes de Juan* (parámetro `dcasa_conversaciones.juan_url`, `addons/dcasa_conversaciones/models/ajustes.py:42-45`) |
| `BRIAN_TELEGRAM_CHATS` | Variable | IDs de los chats de Telegram a los que Brian atiende (coma). Sin ella, cualquiera que encuentre el bot recibe las instrucciones para vincularse ([BRIAN.md › Telegram](../BRIAN.md)) |
| `DCASA_ALERTA_TELEGRAM_CHAT` | Variable | Chat al que el Worker avisa si el contenedor se cae (con el bot de Brian) |
| `TURNSTILE_SITE_KEY` | Variable | Clave pública de Turnstile (o en `edge/wrangler.jsonc`, `:90-91`) |
| `DCASA_SESION_ADMIN_HORAS`, `DCASA_INACTIVIDAD_ADMIN_MIN`, `DCASA_AVISO_LOGIN_TELEGRAM`, `DCASA_ROBOTS_IA`, `DCASA_ALERTA_DISCO_PCT`, `DCASA_ALERTA_MEMORIA_PCT`, `DCASA_ALERTA_BASE_GB`, `DCASA_ALERTA_SILENCIO_H`, `ODOO_LOG_LEVEL`, `ODOO_LOG_HANDLER`, `BRIAN_HERRAMIENTAS_MAX`, `BRIAN_ESFUERZO`, `BRIAN_CACHE` | Variables | Opcionales ([ARQUITECTURA.md §5.3](../ARQUITECTURA.md)) |
| `DCASA_PERMITIR_BAJAR`, `DCASA_HUMO`, `DCASA_2FA_RESCATE`, `DCASA_RESTAURAR_HASTA`, `DCASA_TURNSTILE` | Variables | Salidas de emergencia: solo mientras hagan falta ([OPERACION.md](../OPERACION.md), [SEGURIDAD_ACCESO.md §4](../SEGURIDAD_ACCESO.md)) |

`TELEGRAM_BOT_TOKEN`, `BRIAN_TELEGRAM_SECRETO` y `RESEND_API_KEY` pueden ir en GitHub (§2.2) **o** en este panel. Si
están en GitHub, cada despliegue los sube y reemplaza el valor del panel ([CORREO.md §3](../CORREO.md)). Elegir **un**
lugar por secreto; GitHub tiene la ventaja de quedar separado por environment.

### 3.1 Variables no secretas que van en el código (`edge/wrangler.jsonc`)

Producción en `edge/wrangler.jsonc:57-96`, staging en `:143-176`; para qué sirve cada una, en
[ARQUITECTURA.md §5.2](../ARQUITECTURA.md). Se cambian con un commit y un despliegue (con su prueba,
[VALORES_DE_LA_EMPRESA.md §P](VALORES_DE_LA_EMPRESA.md)):

| Nombre | Qué decide |
|---|---|
| `CANONICAL_HOST` | Dominio con el que Odoo arma sus direcciones (lo pisa el anfitrión de `URL_SITIO` si la variable de GitHub está vacía) |
| `DCASA_ENTORNO` | `produccion` o `staging` |
| `DCASA_STOCK_PRUEBA` | Unidades de prueba por producto (producción siempre `0`) |
| `DCASA_BLACK_WEEKEND`, `DCASA_BLACK_WEEKEND_INICIO`, `DCASA_BLACK_WEEKEND_FIN` | La campaña Black Weekend y su ventana |
| `R2_BUCKET` | El bucket del entorno (obligatoria para arrancar) |
| `ODOO_DORMIR_TRAS` | Vacía = 24/7; una duración (`"1h"`) = duerme sin visitas |
| `TIENDA_ESTATICA`, `TIENDA_AVISO_URL` | Caché de páginas y a dónde avisa Odoo los cambios |
| `DCASA_2FA_OBLIGATORIO`, `DCASA_2FA_ALCANCE` | Doble factor obligatorio y para quién |
| `DCASA_PUERTA_OBLIGATORIA`, `DCASA_PUERTA_EXIGIR_CORREO` | Puerta del equipo (`0`, `avisar`, `1`) y si el correo de Access debe ser el del usuario |

Otras que lee el Worker, opcionales: `DCASA_PUERTA_HORAS` (horas que dura la puerta abierta), `DCASA_ADJUNTOS` (`r2`
por defecto; `db` solo en emergencia), `DCASA_ALERTA_TELEGRAM` (`"0"` apaga los avisos de disco, memoria y base). Los
límites por IP `LIMITE_ACCESO`, `LIMITE_FORMULARIOS` y `LIMITE_CARRITO` son *bindings* de Rate Limiting, hoy
comentados (`edge/wrangler.jsonc:98-106`). `APP_VERSION` la pone el despliegue
(`.github/workflows/desplegar.yml:297-298`) y `VERSION` de Juan, el suyo (`.github/workflows/desplegar-juan.yml:128`):
no se cargan a mano.

## 4. Panel de Cloudflare: Worker `dcasa-juan` / `dcasa-juan-staging`

Ninguno pasa por GitHub (`juan/wrangler.jsonc:43-46`, `.github/workflows/desplegar-juan.yml:12-16`). El Worker arranca
sin secretos y `GET https://dcasa-juan.<subdominio>.workers.dev/salud` dice qué **nombres** faltan
([JUAN_WORKER.md §4](../JUAN_WORKER.md)). Nombres en `juan/src/env.ts:51-64`.

### 4.1 Siempre

| Nombre | Tipo | Para qué |
|---|---|---|
| `JUAN_ODOO_TOKEN`, `JUAN_WORKER_TOKEN` | Secretos | Los mismos valores que en `dcasa` (§6). `JUAN_WORKER_TOKEN` también firma los enlaces temporales de archivos |
| `URL_PUBLICA` | Variable | La dirección de este mismo Worker, sin `/` final. **Sin ella Odoo no puede bajar las fotos, notas de voz y stickers del chat** (trampa conocida, [CONTEXTO_AGENTICO.md](../CONTEXTO_AGENTICO.md)) |
| `ALERTA_TELEGRAM_CHAT_ID` | Variable | Chat al que el cron de salud avisa (se averigua con `/miid` al bot de Juan) |

### 4.2 WhatsApp por la API oficial de Meta (así atiende D'CASA desde el 2026-11-02)

| Nombre | Tipo | De dónde sale |
|---|---|---|
| `WHATSAPP_CLOUD_TOKEN` | Secreto | Llave **permanente** de un usuario del sistema de Meta (Administrador; app y cuenta de WhatsApp con control total; caducidad «Nunca»; permisos `whatsapp_business_messaging` y `whatsapp_business_management`). La del Explorador de la API Graph vence en 1-2 horas: nunca se deja puesta ([LEEME_PRIMERO.md, bitácora 2026-11-02](../LEEME_PRIMERO.md)) |
| `WHATSAPP_PHONE_NUMBER_ID` | Variable | El identificador del número que muestra Meta (no es el celular) |
| `META_APP_SECRET` | Secreto | La clave secreta de la app (firma `X-Hub-Signature-256`) |
| `META_VERIFY_TOKEN` | Secreto | Una frase que **inventa** quien instala (24 a 64 letras y números) y se pone igual en Meta y aquí |
| `GRAPH_API_VERSION` | Variable | Opcional: versión de la API de Meta (`vNN.N`) |

Webhook en Meta: `https://dcasa-juan.<subdominio>.workers.dev/webhooks/whatsapp-cloud`
(`juan/src/canales/whatsappCloud.ts:166`), con el mismo `META_VERIFY_TOKEN`. Qué exige el canal para darse por
configurado: `juan/src/canales/whatsappCloud.ts:172-178`.

### 4.3 Messenger e Instagram (preparados)

`META_APP_SECRET`, `META_VERIFY_TOKEN` (los mismos de §4.2) y `META_PAGE_TOKEN` (la llave de la página). Webhook
`/webhooks/meta`. Paso a paso: [JUAN_META.md](../JUAN_META.md).

### 4.4 Telegram (canal de pruebas de Juan)

`TELEGRAM_BOT_TOKEN_JUAN` (de @BotFather, **otro** bot que el de Brian) y `TELEGRAM_WEBHOOK_SECRET_JUAN` (24 a 64
caracteres: letras sin tilde, números, guion y guion bajo). Webhook `/webhooks/telegram`
([JUAN_WORKER.md §6](../JUAN_WORKER.md)).

### 4.5 La IA

Solo la del proveedor elegido en Odoo (*Ajustes de Juan › proveedor*) y la del respaldo, si hay: `ANTHROPIC_API_KEY`,
`META_AI_API_KEY` u `OPENAI_API_KEY`. Variables opcionales `META_AI_BASE_URL`, `OPENAI_BASE_URL`, `MODELO_VISION`.

### 4.6 WhatsApp por QR (solo con el puente)

`WA_TOKEN`: el mismo valor en Juan y en el puente (§5).

Las variables que sí van en el código (y se cambian con un despliegue de Juan): `ENTORNO`, `URL_SITIO`,
`BUFFER_SEGUNDOS`, `TOPE_DIARIO`, `TRANSCRIBIR_AUDIO`, `RECONOCER_IMAGENES` (`juan/wrangler.jsonc:47-56,78-85`).

## 5. Panel de Cloudflare: Worker `dcasa-puente-wa` (opcional)

El puente de WhatsApp por QR **nunca se desplegó en producción** en D'CASA y con la API oficial no hace falta. Si se
usa: obligatorios `WA_TOKEN` (el mismo de Juan) y **`WA_SESION_CLAVE`** (cifra la sesión; se genera una vez y no se
cambia salvo con la rotación de [JUAN_PUENTE.md §C](../JUAN_PUENTE.md)); opcionales `TELEGRAM_BOT_TOKEN_JUAN`,
`ALERTA_TELEGRAM_CHAT` y `WA_SESION_CLAVE_ANTERIOR` (`puente-wa/wrangler.jsonc:50-57`). Sin los obligatorios arranca
«sin configurar» y `GET /api/estado` dice qué falta.

## 6. Valores que se comparten entre dos Workers

| Valor | Dónde va (el mismo en los dos) |
|---|---|
| `JUAN_ODOO_TOKEN` | `dcasa` y `dcasa-juan` (y sus pares de staging, con otro valor) |
| `JUAN_WORKER_TOKEN` | `dcasa` y `dcasa-juan` |
| `WA_TOKEN` | `dcasa-juan` y `dcasa-puente-wa` |

Son contraseñas que inventa quien instala (32 caracteres al azar, letras y números: `openssl rand -hex 32` sirve).
Nunca el mismo valor para dos secretos distintos, ni entre entornos ([JUAN_WORKER.md §5](../JUAN_WORKER.md)).

## 7. Lo que no se rota nunca (copia en el gestor de contraseñas **antes** del primer despliegue)

| Secreto | Por qué | Cómo se recupera |
|---|---|---|
| `PGBACKREST_CIPHER_PASS` (por entorno) | Cambiarla deja ilegibles los respaldos y corta el archivado del WAL | `cd edge && npx wrangler secret put PGBACKREST_CIPHER_PASS --env=""` (staging: `--env=staging`) pegando la copia ([DESPLIEGUE.md §3](../DESPLIEGUE.md)) |
| `DCASA_PIN_PEPPER` (por entorno) | Cambiarla invalida el PIN de todos los socios (`CLAUDE.md`, regla 6 de Socios) | Ídem con `DCASA_PIN_PEPPER` |
| `WA_SESION_CLAVE` (si hay puente) | Cifra la sesión de WhatsApp | Rotación documentada en [JUAN_PUENTE.md §C](../JUAN_PUENTE.md) |

Cloudflare no deja volver a leer un secreto guardado: la copia de la gerencia es el único respaldo.

## 8. Lo que se configura en Odoo (no son secretos)

| Pantalla | Qué |
|---|---|
| *Ajustes › Empresas* (pestaña «Documentos D'CASA») | Datos de la empresa, garantía, cambios, términos, condiciones de abono, QR en documentos |
| *Sitio web › Configuración › Ajustes* | WhatsApp del sitio, días que se guarda un pedido sin cobrar |
| *Ajustes de Ventas* | Tope de descuento de la Vendedora |
| *Ajustes › Brian* | Tope de gasto de IA (de fábrica no hay tope: [BRIAN.md](../BRIAN.md)) |
| *Conversaciones › Configuración › Ajustes de Juan* | Proveedor y modelos de IA, precios, tope del mes, canales, horario, bienvenida, dirección del Worker de Juan, ajustes de Sofía |
| *Conversaciones › Conocimiento del bot* | Lo que Juan sabe del negocio |
| *Ventas › Configuración › Correo a clientes* | Remitente, respuestas, interruptor «Enviar correos a clientes» |
| *Ajustes › Meta (Facebook e Instagram)* | ID del píxel e interruptores (todo apagado de fábrica) |
| *Ajustes › Programa de vendedores* | Reglas del programa, por versiones hacia adelante |
| *CRM › Configuración › Mensajes de Sofía* | Las plantillas de Sofía |

## 9. Cómo se generan y se cargan sin pasar por el chat

1. Quien instala genera el valor en **su** terminal (`openssl rand -hex 32`) o en el gestor de contraseñas, o lo copia
   del panel del proveedor.
2. Lo guarda en el gestor de contraseñas con el nombre exacto del secreto y el entorno.
3. Lo pega directo en GitHub (*Settings › Environments › <entorno> › Add environment secret*) o en el panel de
   Cloudflare (tipo *Secret*). Nunca en un chat, un correo, un issue, un commit ni un documento.
4. Comprueba que el nombre aparece en la lista (el valor no se ve) y, para los de Juan, que `/salud` ya no lo pide.
