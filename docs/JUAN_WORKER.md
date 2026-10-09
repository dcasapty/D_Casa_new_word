# Juan, el Worker del bot de atención (`juan/`)

Este documento explica **cómo está hecho Juan por dentro**, cómo se le agrega un canal, qué le falta
para funcionar y cómo probarlo con Telegram. El contrato con Odoo y el puente de WhatsApp está en
[`JUAN.md`](JUAN.md); aquí solo está lo que construyó el Worker.

No hay ningún secreto en este documento: solo **nombres**. Los valores los pega la dueña en el panel
de Cloudflare.

## 1. Qué es Juan, en tres líneas

- Un Worker de Cloudflare llamado **`dcasa-juan`** (y **`dcasa-juan-staging`** para ensayar).
- Recibe los mensajes de los clientes por varios canales, espera 15 segundos a que terminen de
  escribir, le pregunta a la IA qué contestar (la IA usa las herramientas de Odoo para no inventar
  nada) y manda la respuesta por el mismo canal.
- **Odoo guarda todo** (conversaciones, clientes, oportunidades). Juan solo guarda lo mínimo para
  contestar bien, en la memoria propia de cada conversación. No usa D1, ni Vectorize, ni R2.

El nombre público que ve el cliente es «el equipo de D'CASA»; el bot se presenta como **asistente
automático** y ofrece una persona. «Juan» es solo el nombre interno.

## 2. Cómo está armado

```
                      cliente
   WhatsApp (QR)   Telegram   Messenger/Instagram   WhatsApp Cloud (apagado)
        |              |               |                     |
        v              v               v                     v
   ┌────────────────────────── Worker dcasa-juan ──────────────────────────┐
   │  rutas.ts  ->  canales/*  (un adaptador por canal, todos iguales)      │
   │                    |                                                   │
   │                    v                                                   │
   │   Durable Object «Conversacion»  (uno por canal:id_externo)            │
   │     ráfaga de 15 s -> IA con herramientas -> guardia de salida         │
   │     -> burbujas cortas -> el canal                                     │
   │   Durable Object «Global»  (uno solo: gasto de IA del mes, salud)      │
   └───────────────────────┬──────────────────────────┬─────────────────────┘
                           │ service binding DCASA     │ service binding PUENTE
                           v                           v
                  Worker dcasa -> Odoo            puente de WhatsApp (QR)
```

### Qué hay en cada carpeta de `juan/src/`

| Archivo o carpeta | Qué hace |
|---|---|
| `index.ts` | Conecta Cloudflare con el resto: recibe las peticiones y el cron de cada hora. |
| `rutas.ts` | Todas las direcciones del Worker: `/health`, `/salud`, `/webhooks/*`, `/media/*`, `/odoo/*`. No depende de Cloudflare, por eso se prueba fácil. |
| `canales/` | Un archivo por canal (`telegram`, `whatsappQr`, `meta` = Messenger e Instagram, `whatsappCloud`). Todos cumplen la misma interfaz (`tipos.ts`). `index.ts` es la lista. |
| `motor/conversacion.ts` | El cerebro de **una** conversación: anti-spam, ráfaga, turno de IA, guardia de salida, seguimiento, cola hacia Odoo. |
| `motor/do.ts` y `motor/global.ts` | Las dos clases de Durable Object (le prestan a lo anterior su base de datos, su reloj y su alarma). |
| `motor/modelo.ts`, `proveedores.ts`, `precios.ts` | Qué modelo contesta (rápido o inteligente), con qué proveedor (Claude, Meta, OpenAI), cuánto cuesta y el tope del mes. |
| `motor/herramientas.ts` | Convierte las herramientas de Odoo en herramientas para la IA, con caché de 60 s para las que solo leen. |
| `motor/almacen.ts` | Las tablas de la memoria de trabajo (últimos mensajes, cola, archivos temporales). |
| `dcasa/prompt.ts` | El prompt de D'CASA: `<fuentes_de_verdad>`, las 11 reglas, la voz de la marca. |
| `dcasa/salvaguardas.ts` | La **guardia de salida**: lo que la IA escribe se revisa antes de llegar al cliente (precios sin «+ ITBMS», números de existencias, promesas de entrega o descuento, fugas del prompt, emojis, «remate»...). |
| `odoo/cliente.ts` | Habla con Odoo por el service binding `DCASA`, con plazos largos y reintentos donde es seguro. |
| `config.ts` | La configuración que la dueña edita en Odoo, con caché de 60 s. |
| `salud.ts` | Lo que contestan `/salud` y `/odoo/salud`, y los avisos del cron. |

### Qué pasa con un mensaje, paso a paso

1. El cliente escribe. El canal llama a `/webhooks/<canal>`. El adaptador **verifica que viene de
   quien dice** (secreto de Telegram, firma de Meta, token del puente) y lo traduce a un mensaje
   igual para todos los canales.
2. Si en Odoo ese canal está apagado, no pasa nada más. Si no, el mensaje va al Durable Object de
   esa persona. Uno por persona: dos mensajes seguidos nunca se pisan.
3. Se anotan en Odoo (el historial es de Odoo). Si Odoo está dormido, el mensaje espera en una cola
   y se manda cuando despierte. No se pierde.
4. Antes de gastar IA: anti-spam (mismo mensaje 3 veces, o más de 50 turnos al día), «¿está pausada
   por una persona?», y «persona / vendedora / humano» (eso pasa a una vendedora **siempre**, sin
   preguntarle a la IA).
5. Se espera 15 segundos por si el cliente sigue escribiendo. Todo lo que dijo en ese rato se
   contesta junto.
6. La IA contesta usando las herramientas de Odoo (hasta 6 pasos). Los archivos del cliente
   (comprobantes, cédulas) **no se le muestran a la IA**: se anotan para una vendedora.
7. La guardia de salida revisa el texto. Si algo está mal, la IA lo reescribe una vez; si insiste,
   esa oración no sale.
8. **Justo antes de enviar** se le pregunta otra vez a Odoo «¿alguien tomó la conversación?». Si sí,
   no se envía.
9. Sale en burbujas cortas, con una pausa de 1 segundo entre ellas. Todo se registra en Odoo.

Si la IA falla, reintenta a los 60 segundos y a los 5 minutos. Si sigue fallando, le dice al cliente
con honestidad que una vendedora lo atiende y avisa a la vendedora. **El cliente nunca se queda sin
respuesta.**

### Gasto de IA

El tope mensual (`presupuesto_ia_mensual_usd`, en Odoo) **no apaga** el bot: al llegar, baja al
modelo barato y sigue contestando. El gasto se calcula con una tabla de precios (sección 8).

## 3. Cómo agregar un canal nuevo

Un canal es un archivo que cumple la interfaz `AdaptadorCanal` (`juan/src/canales/tipos.ts`). Nada
más del Worker cambia: las rutas, el envío y la salud salen de la lista.

1. **Nombre del canal.** Agrégalo a `CanalId` y a `TODOS_LOS_CANALES` en `canales/tipos.ts`, con el
   mismo nombre que usa Odoo (`docs/JUAN.md`). Decide si arranca encendido o apagado en
   `ENCENDIDOS_POR_DEFECTO` (`config.ts`). Los nuevos deben arrancar **apagados**.
2. **Escribe `canales/<canal>.ts`** con una función `crear<Canal>()` que devuelva:
   - `canales` y `ruta` (por ejemplo `/webhooks/signal`).
   - `capacidades(canal)`: si admite imágenes, documentos, si exige la ventana de 24 h y el largo
     máximo de un mensaje.
   - `faltantes(env, canal)`: los **nombres** de los secretos o bindings que le faltan. Esto es lo que
     lee `/salud`. Nunca valores.
   - `recibir(req, env)`: **verifica el origen primero** (firma, secreto o token, en tiempo
     constante, y falla cerrado si el secreto no está cargado) y devuelve los mensajes ya traducidos
     (`Entrante`). Para un archivo que hay que pedir con credenciales, usa `obtener()`: así el token
     nunca sale del adaptador.
   - `enviar(canal, salida, env)`: manda las burbujas y luego las imágenes y documentos.
   - Opcionales: `escribiendo()` (el «escribiendo...») y `salud()` (si hay una conexión que vigilar).
   - Recibe `fetch` y `dormir` como parámetros para que las pruebas no usen la red.
3. **Regístralo** en la lista de `canales/index.ts` (`crearAdaptadores`).
4. **Pruebas** en `juan/test/canales/<canal>.test.ts`: verificación del origen (buena, mala y
   ausente), traducción de texto, imagen, audio y documento, envío, error sin filtrar el token y
   `faltantes`. Copia la forma de `test/canales/meta.test.ts`.
5. Agrega los secretos nuevos a `Env` (`src/env.ts`) y a la tabla de la sección 5 de este documento.
6. En Odoo, agrega el canal a la lista de `canal` (módulo de la bandeja) y a `canales_activos`.

## 4. El primer despliegue (sin ningún secreto)

Juan **arranca sin secretos** y no se cae: por eso el primer despliegue puede hacerse antes de
pegar nada.

1. Se despliega (sección 10). Cloudflare crea el Worker y sus dos Durable Objects.
2. Abre `https://dcasa-juan-staging.dcasapty.workers.dev/salud` (o la de producción). Sin secretos
   dirá algo así:
   ```json
   {"ok": false,
    "mensaje": "Falta ANTHROPIC_API_KEY: el asistente todavía no puede contestar con IA ...",
    "secretos_faltantes": ["JUAN_ODOO_TOKEN", "JUAN_WORKER_TOKEN", "ANTHROPIC_API_KEY"],
    "canales": {"telegram": {"activo": true, "configurado": false,
                             "faltan": ["TELEGRAM_BOT_TOKEN_JUAN", "TELEGRAM_WEBHOOK_SECRET_JUAN"]}, "...": "..."}}
   ```
   Es **público** pero solo muestra nombres y estados: nunca valores, gasto ni motivos de fallo.
3. Pega los secretos que falten en **Cloudflare → Workers → `dcasa-juan` → Settings → Variables and
   Secrets** (tipo *Secret*). Vuelve a abrir `/salud` hasta que `secretos_faltantes` quede vacío.
4. Mientras faltan secretos: los webhooks responden «no autorizado», `/odoo/*` responde 503 diciendo
   qué nombre falta, y si un cliente llegara a escribir sin la clave de la IA, el bot le dice que una
   vendedora lo atiende (y se lo avisa a la vendedora).

Un despliegue nuevo **nunca borra** lo que pegaste en el panel (secretos ni variables).

La versión con más detalle (con staging, tope, estado de la IA y avisos) está en
`GET /odoo/salud`, que pide `Authorization: Bearer <JUAN_WORKER_TOKEN>`.

## 5. Qué secreto, en qué Worker, para qué

| Secreto | En qué Worker | Para qué | Cuándo hace falta |
|---|---|---|---|
| `JUAN_ODOO_TOKEN` | `dcasa-juan` y `dcasa` (mismo valor) | Juan se identifica ante Odoo en cada llamada. | Siempre. |
| `JUAN_WORKER_TOKEN` | `dcasa-juan` y `dcasa` (mismo valor) | Odoo se identifica ante Juan (`/odoo/*`). También firma los enlaces temporales de archivos. | Siempre. |
| `WA_TOKEN` | `dcasa-juan` y el puente de WhatsApp (mismo valor) | Clave compartida entre Juan y el puente. | Cuando se conecte WhatsApp por QR. |
| `ANTHROPIC_API_KEY` | `dcasa-juan` | La IA (Claude). | Mientras `proveedor_ia` sea `anthropic` (lo normal) o `anthropic` sea el respaldo. |
| `META_AI_API_KEY` | `dcasa-juan` | La IA de Meta (Muse Spark). | Solo si en Odoo eliges `meta`. |
| `OPENAI_API_KEY` | `dcasa-juan` | La IA de OpenAI. | Opcional: solo si en Odoo eliges `openai`. |
| `TELEGRAM_BOT_TOKEN_JUAN` | `dcasa-juan` | Enviar mensajes por Telegram. | Para probar con Telegram. |
| `TELEGRAM_WEBHOOK_SECRET_JUAN` | `dcasa-juan` | Comprobar que lo que llega a `/webhooks/telegram` viene de Telegram. | Para probar con Telegram. |
| `META_APP_SECRET` | `dcasa-juan` | Comprobar la firma de Messenger, Instagram y WhatsApp Cloud. | Cuando se encienda Messenger o Instagram. |
| `META_VERIFY_TOKEN` | `dcasa-juan` | Que Meta pueda verificar el webhook. | Ídem. |
| `META_PAGE_TOKEN` | `dcasa-juan` | Enviar por Messenger e Instagram. | Ídem. |
| `WHATSAPP_CLOUD_TOKEN` | `dcasa-juan` | Enviar por WhatsApp Cloud API. | **Solo** si algún día se enciende la Cloud API. Además hace falta la variable `WHATSAPP_PHONE_NUMBER_ID`. |

**Solo hace falta la clave de la IA que elijas en Odoo** (y la del respaldo, si pones uno). `/salud`
pide únicamente esas.

### Los tres valores que se comparten entre dos Workers

`JUAN_ODOO_TOKEN`, `JUAN_WORKER_TOKEN` y `WA_TOKEN` son **contraseñas inventadas por ti** que dos
Workers deben conocer igual. No las da ninguna empresa. Cómo hacerlas:

1. Abre tu administrador de contraseñas y pídele una contraseña **al azar de 32 caracteres** (solo
   letras y números está bien, y es lo más seguro para evitar problemas al copiarla).
2. Guárdala con un nombre claro («JUAN_ODOO_TOKEN»).
3. Pégala **tal cual, el mismo valor**, en los dos Workers que dice la tabla. Si pegas valores
   distintos, los dos Workers no se van a entender y `/salud` o Odoo mostrarán «no autorizado».
4. Haz lo mismo, con una contraseña distinta cada vez, para las otras dos.

No las escribas en chats, en correos, en GitHub ni en este repositorio. **Nunca** uses el mismo valor
para dos secretos distintos.

### Variables (no secretas) que se cambian en el panel

Se pegan en el mismo lugar que los secretos pero como tipo *Text*. No están en el repositorio a
propósito: así un despliegue no las pisa.

| Variable | Para qué |
|---|---|
| `URL_PUBLICA` | La dirección de este mismo Worker (sin barra al final), por ejemplo `https://dcasa-juan.dcasapty.workers.dev`. Sin ella, los archivos que manda el cliente se guardan pero Odoo no recibe un enlace para bajarlos. |
| `ALERTA_TELEGRAM_CHAT_ID` | El chat de Telegram al que el cron avisa si algo se cae. Vacío = sin avisos. Se averigua escribiéndole `/miid` al bot. |
| `WHATSAPP_PHONE_NUMBER_ID` | Solo para WhatsApp Cloud API. |
| `GRAPH_API_VERSION` | Versión de la API de Meta (por ejemplo `v26.0`). Meta retira versiones viejas cada ~2 años; esto permite cambiarla sin tocar el código. |
| `META_AI_BASE_URL`, `OPENAI_BASE_URL` | Solo si hay que apuntar a otra dirección de esas APIs. Vacío = la oficial. |

Las que sí están en `wrangler.jsonc` (y se cambian con un despliegue): `ENTORNO`, `URL_SITIO`,
`BUFFER_SEGUNDOS` (15), `TOPE_DIARIO` (50) y `TRANSCRIBIR_AUDIO` (0).

## 6. Probar con Telegram

Telegram es el canal de **pruebas**: no necesita el número de la tienda ni a Meta.

1. En Telegram, escríbele a **@BotFather**, manda `/newbot` y sigue los pasos. Te da un **token**
   (algo como `123456:ABC...`). Eso es `TELEGRAM_BOT_TOKEN_JUAN`.
2. Inventa el **secreto del webhook**: una contraseña al azar, de 24 a 64 caracteres, **solo letras
   (sin tildes), números, guion y guion bajo** (Telegram no acepta otros). Eso es
   `TELEGRAM_WEBHOOK_SECRET_JUAN`.
3. Pega en `dcasa-juan-staging` (Cloudflare → Variables and Secrets): `TELEGRAM_BOT_TOKEN_JUAN`,
   `TELEGRAM_WEBHOOK_SECRET_JUAN`, `JUAN_ODOO_TOKEN`, `JUAN_WORKER_TOKEN` y `ANTHROPIC_API_KEY`.
4. Dile a Telegram a dónde mandar los mensajes. Abre esta dirección en el navegador, cambiando lo
   que está entre `< >`:
   ```
   https://api.telegram.org/bot<TOKEN_DEL_BOT>/setWebhook?url=https://dcasa-juan-staging.dcasapty.workers.dev/webhooks/telegram&secret_token=<SECRETO_DEL_WEBHOOK>
   ```
   Debe contestar `{"ok":true,"result":true,...}`. (Para quitarlo: `.../deleteWebhook`.)
5. Escríbele «Hola» a tu bot. A los ~15 segundos contesta, se presenta como asistente automático y
   ofrece una persona.
6. Escríbele `/miid`: te dice tu chat id. Pégalo como `ALERTA_TELEGRAM_CHAT_ID` si quieres que los
   avisos de salud te lleguen ahí.
7. Pruebas útiles: «persona» (debe pasar a una vendedora), «cuánto cuesta una cama queen» (debe usar
   el catálogo y decir «+ ITBMS»), «me lo entregan mañana» (debe decir que lo confirma una
   vendedora), mandar una foto (la vendedora la revisa; el bot no la mira).

Si no contesta: abre `/salud` y mira `secretos_faltantes` y `canales.telegram`; después
`/odoo/salud` (con el token) para ver el último fallo de la IA.

## 7. Conectar el puente de WhatsApp (QR)

El puente es otro Worker (`puente-wa/`). Juan le habla por un **service binding**, no por internet.

1. Publica primero el puente (Cloudflare rechaza un binding a un Worker que no existe).
2. En `juan/wrangler.jsonc` quita el `//` de la línea
   `{ "binding": "PUENTE", "service": "dcasa-puente-wa" }` (y la coma de la línea de arriba) y pon el
   **nombre real** del Worker del puente. Haz lo mismo en `env.staging`.
3. Despliega Juan de nuevo.
4. Pega `WA_TOKEN` (el mismo valor) en Juan y en el puente.
5. `/salud` debe mostrar `whatsapp_qr` con `configurado: true`. `GET /odoo/salud` además dice si el
   puente está **conectado** o necesita escanear el QR otra vez (el cron avisa por Telegram).

Los mensajes que una vendedora escribe desde el teléfono llegan marcados como propios: Juan los
registra como de la vendedora y se calla.

## 8. Cambiar de IA desde Odoo (sin tocar código)

Todo se decide en los Ajustes de Odoo, y Juan lo lee con una demora de hasta 60 segundos.

| Campo en Odoo | Qué hace | Por defecto |
|---|---|---|
| `proveedor_ia` | Quién contesta: `anthropic`, `meta` u `openai`. | `anthropic` |
| `modelo_rapido` | El modelo barato, para casi todo. | `claude-haiku-4-5` |
| `modelo_inteligente` | El modelo fuerte: cliente molesto, consulta larga o enredada, búsqueda sin resultado. | `claude-sonnet-5-5` |
| `proveedor_respaldo_ia` | Quién contesta si el principal falla o no tiene clave. Vacío = sin respaldo. | vacío |
| `modelo_rapido_respaldo`, `modelo_inteligente_respaldo` | Los modelos del respaldo. Vacío = los de siempre de ese proveedor. | vacío |
| `precios_ia` | Cuánto cuesta cada modelo, en dólares por millón de tokens (ver abajo). | vacío |
| `presupuesto_ia_mensual_usd` | El tope del mes. Al llegar, baja al modelo barato; no apaga el bot. | 30 |

### Pasar de Claude a Meta (Muse Spark)

1. Pega `META_AI_API_KEY` en Juan.
2. En Odoo: `proveedor_ia = meta`. Si no escribes modelos, usa `muse-spark-1.3` (el estándar).
3. **Carga el precio** en `precios_ia`, por ejemplo:
   ```json
   {"muse-spark-1.3": {"entrada": 1.25, "entrada_cache": 0.15, "salida": 4.25}}
   ```
   Ese precio **no está verificado** (la página oficial no se pudo leer). Confírmalo antes de
   confiar en el tope del mes. Si un modelo no tiene precio, Juan **no lo cuenta como gratis**: usa
   una tarifa de reserva alta y `/salud` avisa «el modelo ... no tiene precio cargado».
4. Recomendado: `proveedor_respaldo_ia = anthropic`. Si Meta falla, contesta Claude y queda anotado.
   Sin respaldo y sin clave, el cliente recibe «una vendedora te atiende» y la vendedora recibe el aviso.

**Cuidado con los modelos `-contributor` de Meta:** ese nivel puede usar los mensajes de los clientes
para entrenar. Juan **nunca lo elige solo**; solo se usa si alguien escribe ese nombre en Odoo a
propósito, y entonces `/odoo/salud` muestra un aviso (la Ley 81 de 2019 exige que el texto de
privacidad lo diga). La recomendación de la auditoría (ronda 3) es no usarlo nunca para D'CASA.

Los precios de Claude (Haiku, Sonnet, Opus) vienen integrados, sacados de la ronda 7. Revísalos
cuando Anthropic los cambie.

### Lo demás que se edita en Odoo

`nombre_publico`, `bot_activo_global` (apaga todo), `canales_activos` (cada canal por separado),
`horario` (inicio, fin, días, zona), `seguimiento` (a las 5 h y a los 5 días, máximo 2, solo en
horario laboral), `mensaje_bienvenida` (si dice que es automático, reemplaza a la presentación de
Juan), `texto_privacidad_corto` (se agrega a la primera respuesta), `palabras_prohibidas`,
`pausa_por_defecto_minutos` (120) y `lecciones` (lo que las vendedoras aprendieron; máximo 20
líneas; ayudan con el tono y el modo de atender, **nunca** son fuente de precios ni de políticas).

## 9. Qué datos usa Juan y de dónde (para que nadie los invente)

Precios, existencias, medidas, combos, horario, dirección, cifras de Socios, políticas: **solo** de
las herramientas de Odoo. El prompt no tiene ni un precio ni una cifra. Las herramientas son las 9
del contrato más 2 de la base de conocimiento: `buscar_productos`, `ver_producto`, `listar_categorias`, `reglas_socios`,
`horario_y_tienda`, `saldo_puntos`, `crear_oportunidad`, `anotar_conversacion`, `pasar_a_vendedora`,
`buscar_conocimiento` y `registrar_pregunta_sin_respuesta`; más una local, `enviar_foto_producto`.

Si el cliente pregunta algo que la base de conocimiento no responde, Juan **no inventa**: lo dice, y
la pregunta queda registrada en Odoo para que una persona la conteste y la agregue.

## 10. Desplegar

El workflow es **manual**: `.github/workflows/desplegar-juan.yml` (Actions → *Desplegar Juan* → *Run
workflow*). No lo llama el CI y **todavía no se ha ejecutado**.

- Elige `staging` o `production` y deja marcado **dry_run** para solo validar el paquete (no toca
  Cloudflare y no necesita credenciales).
- Sin dry_run, además de validar, despliega con `--keep-vars` y deja en el resumen lo que contesta
  `/salud`.
- Solo usa los dos secretos de GitHub que ya existen para desplegar (`CLOUDFLARE_API_TOKEN` y
  `CLOUDFLARE_ACCOUNT_ID`). **Ningún secreto de Juan pasa por GitHub.**
- El binding `DCASA` lleva `"entrypoint": "JuanEntrada"` (la clase del Worker `dcasa` que reenvía a Odoo): sin él, el Worker `juan`
  llamaría al `fetch` público de `dcasa`, donde `/dcasa/juan/**` da 404 (`test/despliegue.test.ts` lo vigila).
- Antes del primer despliegue real tienen que existir los Workers a los que apunta `services`:
  staging apunta a `dcasa-staging` y producción a `dcasa`. Cloudflare rechaza el despliegue si el
  destino del binding no existe.
- Los Durable Objects (`Conversacion` y `Global`) se crean con la migración `v1` del propio
  despliegue. **Es un recurso nuevo en Cloudflare**: por eso este workflow espera la aprobación de
  la dueña, y en `production` conviene exigir «Required reviewers» en el *environment*.

Comandos locales: `cd juan && npm ci && npm test && npm run typecheck`, y para validar el paquete
`npx wrangler deploy --dry-run` (producción) o `npx wrangler deploy --dry-run --env=staging`.

## 11. Salud y avisos

- `GET /health` responde `ok` (sin datos).
- `GET /salud` (público) y `GET /odoo/salud` (con token): ver sección 4. El segundo agrega el gasto
  del mes, el tope, el estado de la IA (qué proveedor, último fallo, si contestó el respaldo), los
  modelos sin precio y los avisos.
- **Cron cada hora** (minuto 23 UTC): revisa lo mismo y, si hay un problema **nuevo**, avisa por
  Telegram al `ALERTA_TELEGRAM_CHAT_ID`: un secreto que falta en un canal encendido, el puente
  desconectado, la IA fallando, el tope alcanzado. **Avisa una sola vez** por problema y avisa
  «Resuelto» cuando se arregla.

## 12. Notas de voz (apagado)

Por defecto una nota de voz **no se transcribe**: Juan le pide al cliente que escriba, o le dice que
una vendedora la escucha. Para transcribir con Whisper de Workers AI hay que **ambas cosas**:
`"TRANSCRIBIR_AUDIO": "1"` en `wrangler.jsonc` y declarar el binding `"ai": { "binding": "AI" }`.
No se activa solo porque Workers AI no debe ser obligatorio, y el audio de un cliente es dato personal.

## 13. Pruebas

`cd juan && npm test`. Hay más de 700 pruebas y no usan la red ni a ningún proveedor real: la IA es
un modelo guionado (o un servidor falso que se porta como la API de Meta), Odoo es un doble, y los
Durable Objects corren sobre SQLite de Node.

| Dónde | Qué prueban |
|---|---|
| `test/dcasa/` | El comportamiento del bot visto desde el cliente: las 11 reglas, `<fuentes_de_verdad>`, que no invente precios ni existencias, que no prometa entrega/flete/financiamiento/apartado/descuento, que los comprobantes y cédulas no lleguen a la IA, resistencia a la inyección de prompt, «persona» siempre pasa, anti-spam, seguimiento, Socios, fotos, base de conocimiento, la voz de la marca, proveedores de IA y precios. |
| `test/canales/` | Cada adaptador: verificación del origen, traducción de mensajes, archivos, envío y errores sin filtrar tokens. |
| `test/odoo/`, `test/config.test.ts` | El cliente de Odoo (rutas, reintentos, plazos) y la configuración (normalización, caché de 60 s, horario). |
| `test/rutas.test.ts` | Todas las direcciones: `/odoo/*` con token, `/media` firmado, webhooks, canal apagado, y que no sobreviva ninguna ruta del CRM de Baby Caleb. |
| `test/punta-a-punta.test.ts` | Telegram -> ráfaga -> IA -> respuesta -> Odoo, con las clases reales de Durable Object, el cron y el primer despliegue sin secretos. |
| `test/despliegue.test.ts` | La configuración de Cloudflare: el binding `DCASA` entra por `JuanEntrada` (con `entrypoint`), producción y staging iguales. |
| `test/integracion/` | **Con el Odoo de verdad** (no un doble): se omite sin `ODOO_INTEGRACION_URL`; la corre `scripts/integracion_juan.sh`. Ver «Contrato verificado» en `JUAN.md`. |

> Los dobles de Odoo de las demás pruebas **hablan como el Odoo real** desde la integración: `pasar_a_vendedora` devuelve
> `texto_para_el_cliente`, `/mensaje` y `/estado` traen `nota_para_el_bot` y los días del horario son `0 = domingo`.

## 14. Qué falta (y qué decide la dueña)

**Falta para que funcione de verdad** (nada de esto es código):

1. Crear/confirmar en Cloudflare los Workers a los que apunta Juan (`dcasa` y `dcasa-staging`) y, para
   WhatsApp, el puente. Aprobar los recursos nuevos (el Worker `dcasa-juan` y sus dos Durable Objects).
2. Pegar los secretos de la sección 5 (los tres compartidos se inventan; la clave de la IA se saca
   del proveedor).
3. Que la pieza de Odoo (`addons/dcasa_conversaciones`) exponga lo que dice `JUAN.md`, **más** los
   campos y herramientas que Juan usa y el contrato original no traía (ver abajo).
4. Para WhatsApp: descomentar el binding `PUENTE` (sección 7).

**Diferencias con `JUAN.md`** (ampliaciones pedidas después del contrato; no rompen nada si Odoo
no las manda, Juan usa valores por defecto):

- `/config` puede traer también `proveedor_ia`, `proveedor_respaldo_ia`, `modelo_rapido_respaldo`,
  `modelo_inteligente_respaldo`, `precios_ia` y `lecciones`.
- `/herramientas` incluye `buscar_conocimiento` y `registrar_pregunta_sin_respuesta` (11 en total).
- `/salud` es público (solo nombres y estados) además del `GET /odoo/salud` del contrato.
- `GET /media/<conversación>/<id>?exp=&sig=`: enlace temporal y firmado (2 días) para que Odoo baje
  los archivos que manda el cliente.

**Decisiones que necesita la dueña:**

1. **Meta como IA.** Si se va a usar, hay que verificar el precio y decidir si el nivel `contributor`
   queda **prohibido** (lo más seguro; hoy Juan solo lo acepta si alguien lo escribe en Odoo y avisa).
2. **Notas de voz.** ¿Se transcriben con Whisper (cuesta y trata el audio del cliente) o se le pide al
   cliente que escriba?
3. **WhatsApp Cloud API.** Está completo pero apagado. El formato de los mensajes que la vendedora
   escribe desde su app (coexistencia) **no está verificado** contra la documentación de Meta (estaba
   bloqueada al construirlo): hay que revisarlo antes de encenderlo.
4. **Tope diario de 50 turnos por persona** y descanso de 1 hora si repite el mismo mensaje 3 veces:
   están en los valores del contrato; se pueden cambiar (`TOPE_DIARIO`).
