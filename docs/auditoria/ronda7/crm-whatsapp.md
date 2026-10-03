# Ronda 7 — «Juan»: el CRM de WhatsApp con IA, dentro de D'CASA

Fecha: 2026-10-02. Análisis de solo lectura del repositorio
`juanarrietabusiness-pixel/crm-baby-caleb` (clonado en esta sesión) contrastado con nuestro
Odoo (`addons/`, `edge/`, `docs/`). **No se escribió código, no se tocó Cloudflare, no se
desplegó nada.**

Leyenda (la misma de la ronda 5):

- **VERIFICADO-CÓDIGO**: leído en el código, con archivo y línea.
- **SEGÚN FUENTE**: lo dice una página externa (vía buscador). El proxy de esta sesión
  **bloqueó** `developers.facebook.com`, `whatsapp.com`, `twilio.com`, `cm.com` y otros, así
  que las tarifas y reglas de Meta **no quedaron leídas de primera mano**.
- **ESTIMACIÓN**: cuenta hecha con supuestos escritos al lado.
- **NO VERIFICADO**: hay que confirmarlo antes de decidir.

Nombres: **Brian** atiende hacia adentro (equipo). **Juan** atendería hacia afuera (clientes
por WhatsApp). «El CRM» es el proyecto de Baby Caleb (marca Juancito Ads); «el puente» es su
carpeta `puente-wa/`.

---

## Resumen ejecutivo (10 líneas)

1. **El CRM está bien hecho y funciona**: ~21.000 líneas, 903 pruebas automáticas, bitácoras
   honestas de cada tropiezo. Es un motor genérico (Worker de Cloudflare + IA) con una capa
   específica de Baby Caleb (carpeta `member/`, catálogo en su propia base, pruebas del documento
   de la dueña de Baby Caleb) que no nos sirve y hay que quitar.
2. **Son dos proyectos en Cloudflare porque WhatsApp por código QR necesita un programa encendido
   las 24 horas** sosteniendo una conexión con WhatsApp (un contenedor). El CRM no lo necesita.
   Están separados a propósito: si el contenedor falla, el CRM sigue publicándose.
3. **El QR es automatización NO oficial** (librería Baileys). Viola los términos de WhatsApp y
   **el riesgo real es que bloqueen el número**, que en D'CASA es **+507 6026-1919, el número de
   ventas**. El propio CRM lo llama «canal alterno» y exige dejar la API oficial conectada.
4. **La API oficial de Meta (Cloud API) es la vía segura**: responder a un cliente dentro de las
   24 h de su mensaje es gratis; solo se paga por mensajes de plantilla que inicia el negocio
   (≈ $0.011 a $0.085 cada uno para Panamá, SEGÚN FUENTE). Con «coexistencia», el mismo número
   sigue en la app del teléfono **y** en la API.
5. **Lo que le falta a la dueña —enviar imágenes y archivos— falta en los dos canales del CRM**
   (hoy solo mandan texto, VERIFICADO-CÓDIGO). Es trabajo pequeño-mediano en cualquier camino.
6. **Recomiendo la opción C (híbrido)**: reutilizar el motor del CRM y el puente, pero con **Odoo
   como única fuente de datos** (catálogo, stock, precios, combos, Socios) y como **bandeja de las
   vendedoras**; el catálogo, los leads y los tickets duplicados del CRM se retiran.
7. **Juan nunca toca lo delicado**: lee catálogo y reglas de Socios (cifras solo de
   `puntos.json`), crea oportunidades y notas en la ficha del cliente, y pasa con una vendedora.
   Jamás escribe puntos, precios, facturas, pagos ni ve datos de otros clientes.
8. **Costo mensual adicional estimado: ≈ $10 a $40** (contenedor del puente ≈ $2 solo si se usa
   el QR; IA ≈ $8 a $31 según modelo y volumen; WhatsApp oficial $0 por respuestas; seguimientos
   con plantilla ≈ $0.01–0.09 cada uno). El plan Workers Paid ($5) ya se paga.
9. **Tiempo**: Fase 0 decisiones (1 semana), Fase 1 prueba cerrada con número de prueba de Meta
   (2–3 semanas de trabajo), Fase 2 piloto con el número real (2 semanas), Fase 3 afinar.
10. **Lo que necesito de la dueña**: confirmar que +507 6026-1919 está en la app **WhatsApp
    Business** (no WhatsApp normal), crear y verificar el Meta Business (RUC 155779346-2-2026
    DV7, aviso de operación), fijar presupuesto y modelo de IA, horario y quién atiende, aprobar
    el nombre público del bot y el texto de privacidad. Detalle en la sección 6.

---

## 1. Qué es el CRM, leído completo

### 1.1 Identidad y origen

- Marca **Juancito Ads**; el repo es el bot de un cliente, **Baby Caleb** (pañales
  hipoalergénicos, Ciudad de Panamá). `CLAUDE.md:1-9`, `wrangler.toml:66-69`.
- Derivado de **CRM-PanaClaw** (abrinay1997-stack) que deriva de **Forja** (santmun); los tres
  MIT. `README.md` «Créditos y origen», `LICENSE`. Se puede usar y modificar comercialmente
  conservando los avisos de copyright.
- Tamaño: **21.240 líneas** de TypeScript/JS en `src/` + `puente-wa/`; **903 pruebas** (`it(`)
  en ~90 archivos con vitest + miniflare (VERIFICADO-CÓDIGO, conteo de esta sesión; el README
  dice 458 — está desactualizado).
- El clon trae **un solo commit** visible (`1e1adaf`, «Respaldo de la base de conocimiento del
  panel (2026-10-02)»): no hay historial para auditar la evolución; las bitácoras en `docs/`
  lo sustituyen.

### 1.2 Arquitectura

```
WhatsApp (Cloud API) ─┐
Telegram ─────────────┤  webhooks         ┌──────────────────────────────────────┐
Messenger/Instagram ──┼──────────────────▶│ Worker "juancitoads-bot" (Hono)      │
Twilio / ManyChat ────┤                   │  · Durable Object SupportAgent       │
WhatsApp por QR ──────┘  (vía el puente)  │    (buffer 15 s + bucle de IA)       │
                                          │  · Panel /admin (htmx, 1 contraseña) │
                                          │  · crons: seguimiento, purga, análisis│
                                          └──┬──────────┬──────────┬────────────┘
                                             │ D1       │ Vectorize│ Workers AI
                                             │ (SQLite) │ (RAG)    │ (Whisper, bge-m3)
                                             ▼          ▼          ▼
            IA (ai-sdk v6): Anthropic / OpenAI / xAI con llave propia

Worker "juancitoads-bot-wa" (el puente) ── Durable Object + Container "lite"
   · Baileys (WhatsApp Web) sostiene el WebSocket 24/7
   · credenciales en su propia D1 (wa_auth)
   · cron cada minuto + vigilancia cada 30 s
```

Fuentes: `wrangler.toml`, `puente-wa/wrangler.toml`, `src/index.ts`, `src/agent.ts`,
`puente-wa/src/worker.ts`, `puente-wa/contenedor/servidor.mjs`.

Piezas de Cloudflare que usa (todas en la cuenta del cliente): Workers Paid, Durable Objects
(dos clases), D1 (dos bases), Vectorize (índice `juancitoads-bot-kb`), Workers AI, Containers
(instancia `lite`), Cron Triggers, service bindings. R2 está declarado pero **apagado**
(`wrangler.toml:35-41`).

### 1.3 Por qué son DOS proyectos («se trata de forma distinta por alguna razón»)

Las razones están escritas en el código, no son capricho:

1. **WhatsApp Web no tiene webhooks.** Alguien tiene que sostener una conexión permanente; un
   Worker vive milisegundos. Por eso hace falta un **contenedor**
   (`puente-wa/contenedor/servidor.mjs:1-5`, `docs/plan-whatsapp-qr.md` §0).
2. **Despliegue separado a propósito**: si la imagen del contenedor no construye, el que no sale
   es el puente y el CRM sigue publicándose; un cambio de la base de conocimiento no puede
   quedarse sin publicar porque WhatsApp esté roto (`puente-wa/wrangler.toml:1-8`,
   `.github/workflows/puente-wa.yml`).
3. **Cloudflare rechaza que un Worker llame a otro de la misma cuenta por URL pública** (error
   1042): los dos se hablan por *service bindings* en ambos sentidos, y por eso el primero
   tiene que existir antes de desplegar el segundo (`wrangler.toml:43-58`,
   `puente-wa/wrangler.toml:29-35`).
4. **El contenedor vive mientras vive su Durable Object**: hubo una noche entera con el canal
   mudo porque el DO se desalojaba entre latidos. Lo arreglaron extendiendo la clase `Container`
   de Cloudflare, programando vigilancia cada 30 s y un cron de plataforma cada minuto como
   «desfibrilador» (`puente-wa/src/worker.ts:16-40`, `docs/bitacora-whatsapp-qr.md` «La causa
   raíz»).

### 1.4 Cómo se conecta WhatsApp por QR (y dónde vive la sesión)

- Librería: `@whiskeysockets/baileys ^7.0.0-rc.12` (no bajar de rc.12: aviso de seguridad
  GHSA-qvv5-jq5g-4cgg en rc.9; `docs/plan-whatsapp-qr.md` §3.3). Imagen Node 22 en dos etapas
  (`puente-wa/contenedor/Dockerfile`).
- **Sesión persistente en D1, no en disco**: el disco del contenedor es descartable. Las
  credenciales (`creds`) y las llaves de Signal (pre-keys, sesiones, `lid-mapping`) se guardan
  como filas en la tabla `wa_auth` de la base `juancitoads-bot-wa-auth`, a través del Worker
  puente (`/puente/kv`, `/puente/kv-lote`). Mientras exista la fila `creds`, no pide QR nuevo
  (`puente-wa/esquema.sql`, `servidor.mjs` `useD1AuthState`).
- **El almacén por lotes es lo que hace vinculable el canal**: al emparejar, WhatsApp exige
  subir 812 llaves en < 30 s; de a una tardaba ~95 s y moría a medias (`docs/plan-whatsapp-qr.md`
  §5). Pasó inadvertido en el piloto porque la señal que miraron salía verde con el dispositivo
  a medio instalar — una lección que ellos mismos subrayan.
- **Instancia única** (`max_instances = 1`): dos sockets sobre el mismo número se expulsan en
  bucle (`puente-wa/wrangler.toml:62-65`).
- Reconexión con espera creciente, vigilante interno cada 30 s, `unhandledRejection` capturado
  (una promesa suelta mataba Node 22 y el contenedor entraba en ciclo de caídas), QR que vence a
  los 45 s (un QR viejo hace que el teléfono diga «revisa tu conexión»). Todo en `servidor.mjs`.
- **Mensajes propios**: el bot anota el id de cada envío **antes** de mandarlo; un mensaje que
  sale del número y no está anotado lo escribió una persona desde el teléfono → se avisa al CRM
  y el bot se calla en esa conversación (`puente-wa/contenedor/propios.mjs`, `src/takeover.ts`).
- **Estados, grupos, canales y bots de Meta se ignoran** (antes el bot «contestó» estados
  publicando con el número del negocio; `servidor.mjs` `esChatDeUnaPersona`).
- **Notas de voz y fotos** se descargan en el contenedor en el momento (Baileys no deja URL
  para después) y viajan en base64 al CRM, que las guarda dos días en D1 (`media_temporal`)
  con URL firmada (`src/media/almacen.ts`).
- Costo medido por ellos: contenedor `lite` encendido 24/7 **≈ $1.50–2.00/mes** sobre Workers
  Paid (`docs/conectar-whatsapp-qr.md`). Cuadra con la tarifa oficial (sección 5).
- **El costo del Durable Object + cron a 24 h no lo midieron** (deuda anotada en la bitácora).

### 1.5 Canales que trae

| Canal | Ruta | Estado en Baby Caleb |
|---|---|---|
| WhatsApp por QR (Baileys) | `/webhooks/whatsapp-qr` | en producción, «alterno» |
| WhatsApp oficial (Cloud API de Meta) | `/webhooks/whatsapp` | adaptador completo (`src/channels/whatsapp.ts`), usado con número de prueba de Meta |
| Twilio WhatsApp | `/webhooks/twilio` | adaptador + plantillas HSM para campañas |
| Messenger / Instagram (Meta oficial) | `/webhooks/meta` | adaptador |
| ManyChat | `/webhooks/manychat` | adaptador |
| Telegram | `/webhooks/telegram` | clientas **y** consola de la dueña en el mismo bot |

### 1.6 Modelo de datos (D1 `juancitoads-bot-db`, `src/db/schema.sql`)

`conversations` (una por canal + id del cliente, con `paused_until` y `open_ticket_id`),
`messages` (rol user/assistant/owner/tool, tokens y modelo usados, **se purgan a los 90 días**),
`leads`, `tickets`, `settings` (configuración editable desde el panel: prompt, contexto,
modelo, presupuesto, herramientas apagadas…), `conversation_insights` y `customer_facts`
(memoria por cliente que escribe un analista nocturno), `kb_docs` + `kb_indice` (base de
conocimiento del panel y espejo de lo indexado en Vectorize), `improvement_suggestions`
(flywheel), `followup_sends`/`seguimientos`/`compras` (seguimiento), `tracked_links`,
`keyword_hits`, `conv_labels`, `template_sends` (campañas), **`catalog_items`** (código,
nombre, costo, precio, stock por bodega; el costo nunca sale hacia el bot), `stock_movements`,
`owner_actions`/`owner_notices`/`owner_chat`/`owner_fotos` (consola de Telegram),
`media_temporal`.

### 1.7 Flujo de un mensaje (VERIFICADO-CÓDIGO)

1. WhatsApp → Baileys en el contenedor (`messages.upsert`): descarta propios ya anotados,
   historial (`append`), estados/grupos; descarga audio/foto; `POST /puente/entrante` con el
   token en base64.
2. Puente → service binding `CRM` → `POST /webhooks/whatsapp-qr` (valida `WA_TOKEN` en tiempo
   constante; `src/index.ts:107-137`).
3. El Worker ubica el Durable Object de esa persona (`channel:channelUserId`) y llama
   `ingest()` (`src/agent.ts:70-205`): crea/lee la conversación en D1; **si una persona la tiene
   (pausa) o el bot está apagado, guarda el mensaje y no contesta**; guardas anti-spam (mensaje
   repetido → 1 h de descanso; tope diario → despedida y 12 h); audio → Whisper en Workers AI;
   imagen → marcador; **espera 15 s** (`BUFFER_SECONDS`) juntando lo que la persona siga
   escribiendo.
4. `processBuffer()` (`src/agent.ts:258-603`): últimos 20 mensajes; herramientas activas según el
   panel; prompt del sistema (cacheado en Anthropic) + `<cliente>` con lo que se recuerda de esa
   persona; **elige modelo**: `fast` (barato) por defecto, `smart` si hubo muchas herramientas,
   frustración o búsqueda floja (`src/upgrade/modelSelector.ts`); **tope de presupuesto mensual**
   que baja al modelo barato, nunca se calla por dinero (`src/budget.ts`); `streamText` con hasta
   6 pasos de herramientas; si el proveedor falla, reintenta y cae al otro proveedor con llave;
   **vuelve a comprobar que nadie tomó la conversación** antes de enviar; guarda tokens y
   herramientas usadas.
5. La respuesta se parte en «burbujas» (`src/replies/chunker.ts`) y sale por el adaptador del
   canal → puente `/api/enviar` → contenedor `sendMessage` con 1 s entre burbujas
   (`servidor.mjs:685-700`). **Solo texto.**

### 1.8 La IA

- **Capa**: Vercel AI SDK v6 con `@ai-sdk/anthropic`, `@ai-sdk/openai`, `@ai-sdk/xai`
  (`package.json`, `src/llm/provider.ts`). Proveedor por `LLM_PROVIDER` o por qué llave existe;
  el panel puede poner proveedor, llave y modelo propios («BYO»).
- **Modelos por nivel**: `fast` = `claude-haiku-4-5-20251001`, `smart` =
  `claude-sonnet-4-5-20250929` (`src/llm/provider.ts:17-20`). **Identificadores viejos**: hoy
  los vigentes son `claude-haiku-4-5` y `claude-sonnet-5-5` (ficha de modelos de Anthropic
  cargada en esta sesión). La lista «curada» del panel llega hasta Opus 4.6. La tabla de precios
  interna (`src/pricing.ts`) tiene Haiku a $0.80/$4 por millón; hoy es $1/$5 → la pestaña
  Costos **subestima**. Se corrige al portar.
- **Caché de prompt** solo con Anthropic (`supportsPromptCache`); OpenAI/xAI pagan el prompt
  entero cada turno.
- **Prompt del sistema** (`src/system-prompt.ts`): idioma obligatorio, **forma de trato**
  (`usted` / `tu` / `vos`, con recordatorio al final porque los modelos pequeños pesan lo
  último que leen), rol, `<business_context>` (de `member/config.local.ts` o del panel),
  principios (una pregunta a la vez, respuestas cortas, escalar temprano, **admitir que es un
  bot**), **`<fuentes_de_verdad>`** («antes de nombrar un producto, precio o existencia, llama
  `catalogQuery`; si no aparece, NO EXISTE; tarifas que no son producto salen de `searchKb`»),
  playbook del giro, lecciones aprendidas, instrucciones del dueño, reglas de escalado, guía de
  estilo, anti-patrones. Es una disciplina muy parecida a nuestra regla 4 («no inventar»).
- **Herramientas** (`src/tools/`): `searchKb` (Vectorize, bge-m3, topK 8), `handoffHuman`
  (ticket + aviso a Telegram/correo/WhatsApp del dueño), `pauseBot`, `snoozeUser`, `captureLead`,
  `scheduleAppointment` (Cal.com), `catalogQuery` (D1; devuelve «disponible / pocas / agotado»,
  **nunca el número exacto ni el costo**; con `cantidad` responde si alcanza), `cotizarEnvio`
  (tabla de zonas de Baby Caleb).
- **Base de conocimiento «conocimiento»**: dos dueños sin temas en común —
  `member/conocimiento/*.md` (lo edita la agencia en GitHub; `pnpm conocimiento` lo compila a
  `src/kb/conocimiento.generado.ts`) y los documentos del panel (`kb_docs`, que la dueña cambia
  desde `/admin/kb` o por Telegram). Ambos se trocean (~1.200 caracteres) e indexan en
  Vectorize; `kb_indice` permite borrar lo que ya no existe (`src/kb/docs.ts`,
  `docs/FUENTES_DE_VERDAD.md`). **Regla de oro: ningún precio en la base de conocimiento ni en el
  contexto** — un precio en el prompt le gana al catálogo sin que nadie lo note; hay pruebas que
  lo vigilan (`test/babycaleb/kb.test.ts`). Es exactamente el error que ya pagaron en producción
  (`docs/AUDITORIA_CONOCIMIENTO.md`).
- **Consola de la dueña por Telegram** (`src/owner/`): avisos con botones (devolver al bot,
  pausar, registrar venta), responder sobre el aviso y que le llegue a la clienta, comandos
  (`/pendientes`, `/venta`, `/stock`, `/seguimiento`, `/compro`…), asistente interno con memoria
  que entiende notas de voz y fotos; lo que sale hacia afuera o mueve inventario **se propone con
  botones**, nunca se ejecuta solo (`docs/consola-del-dueno.md`).
- **Seguimiento** (`src/followup/run.ts`): cron horario; solo a interesadas (el bot consultó
  catálogo/envío o anotó lead), a las 5 h / 3 d / 7 d; nunca si la dueña escribió último; quien
  compró descansa 15 días; **respeta la ventana de 24 h** de WhatsApp oficial/Meta (fuera de
  ventana solo sale por QR y Telegram).
- **Analista nocturno** (Haiku) que resume cada conversación, detecta huecos de la base de
  conocimiento y propone mejoras; «modo copiloto» que las aplica solo (`src/insights/`,
  `src/flywheel/`).
- **Campañas** por segmento con plantillas HSM (solo Twilio; `src/campaigns.ts`).
- Defensas: anti-spam (`src/spam.ts`), watchdog que avisa si el bot falla en cadena
  (`src/watchdog.ts`), presupuesto mensual, `escalar_media` (una foto NO se le muestra a la IA
  y crea ticket: nadie da por bueno un comprobante que no verificó una persona; `src/agent.ts:308-340`).

### 1.9 «Portal member»

No es un portal web: es la **carpeta `member/`**, el espacio del negocio que no se pisa al
actualizar la plantilla (`CLAUDE.md`): `config.local.ts` (identidad, trato, horarios, pagos,
límites duros), `system-prompt.local.ts` (override, vacío), `zonas-envio.ts` (tarifario de
delivery), `conocimiento/*.md`, `kb-respaldo/` (copia diaria del panel, no se lee),
`kb-retirados.json`. Todo es de Baby Caleb.

### 1.10 Panel `/admin`

Hono + htmx, **una sola contraseña** (`DASHBOARD_PASSWORD`, usuario `admin`), pensado para
el teléfono (`docs/design-system.md` es contrato). Pestañas: Resumen, Conversaciones (con
«Enviar», «Pausar», «Devolver», «Sugerir»), Leads, Tickets, Agente (prompt), Config, KB,
Catálogo (editor), Conexiones (incluida la tarjeta del QR con el código y «Reiniciar el
servicio»), Costos, Insights, Mejoras, Campañas (`src/admin/routes.ts`, `src/admin/views/`).

### 1.11 Pruebas, despliegue y secretos

- **Pruebas**: vitest + miniflare; `test/babycaleb/` compara los archivos del repo con el
  documento de la dueña transcrito (`verdad-del-cliente.ts`); `pnpm auditar` compara **la base
  en vivo** contra ese documento (solo `SELECT`) y corre los lunes y tras cada despliegue.
- **Despliegue**: `.github/workflows/deploy.yml` en cada merge a `main`: typecheck + css/icons
  check + tests → aplica esquema D1 → carga secretos → `wrangler deploy` → reindexa la base de
  conocimiento **y reintenta hasta que conteste la versión nueva** → auditoría informativa.
  `puente-wa.yml` aparte (wrangler **clavado en 4.132.0** porque una versión nueva rompió el
  despliegue sin tocar nada; necesita el permiso **Cloudflare Images: Edit**; crea la D1,
  aplica el esquema, sube `WA_TOKEN`, despliega y **reinicia el contenedor** para que tome la
  imagen). También `respaldar-kb.yml` (diario), `ver-logs-puente.yml` (logs sin terminal),
  `auditar.yml`.
- **Secretos** (`wrangler.toml:71-95`, `src/env.ts`): `ANTHROPIC_API_KEY` (o `OPENAI_API_KEY` /
  `XAI_API_KEY`), `DASHBOARD_PASSWORD`, `KB_REINDEX_TOKEN`, `WA_TOKEN` (mismo valor en bot,
  puente y contenedor; **solo ASCII**, ≥ 24 caracteres: un token con ñ o tilde pasa toda prueba
  por navegador y falla solo en la máquina), `TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_CHAT_ID`;
  opcionales `RESEND_API_KEY`/`OWNER_EMAIL`, Twilio (4), WhatsApp Cloud
  (`WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_VERIFY_TOKEN`,
  `WHATSAPP_APP_SECRET`, `WHATSAPP_WABA_ID`), Meta (`META_*`, `INSTAGRAM_*`), `MANYCHAT_API_KEY`,
  `CALCOM_*`, `CONTROL_PLANE_TOKEN`. En GitHub: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
- **Privacidad** (`PRIVACY.md`, `src/legal.ts`): sin telemetría; mensajes 90 días; audios e
  imágenes no se guardan (solo el texto; los del QR, 2 días); el texto viaja al proveedor de IA;
  páginas públicas `/privacidad`, `/terminos`, `/eliminar-datos` que Meta exige para aprobar
  la app.

### 1.12 Qué es de Baby Caleb y qué es genérico

| Específico de Baby Caleb (se quita o se reemplaza) | Genérico (se reutiliza) |
|---|---|
| `wrangler.toml` (nombres, ids de D1, URLs, `BOT_NAME`, `BUSINESS_NAME`, `WA_PUENTE_URL`) | Motor: `src/agent.ts`, `src/index.ts`, `src/takeover.ts`, `src/replies/`, `src/spam.ts`, `src/watchdog.ts`, `src/budget.ts` |
| `member/` completo (trato de **usted**, horarios, Yappy @babycalebpanama, zonas de delivery, conocimiento de pañales) | Canales: `src/channels/*` (Cloud API, Meta, Telegram, QR), `puente-wa/` entero (solo cambia el prefijo de nombres y `browser: ["Baby Caleb", …]` en `servidor.mjs:264`) |
| `test/babycaleb/*` y `scripts/auditar-verdad.ts` (verdad del documento de Yulilka Godoy) | Prompt y disciplina de fuentes de verdad (`src/system-prompt.ts`), herramientas `searchKb`, `handoffHuman`, `pauseBot`, `snoozeUser`, `captureLead` |
| Catálogo en D1: `catalog_items`, `src/db/catalog.ts`, `src/catalog/validation.ts` (3 bodegas de Panamá), `seed-catalog.sql`, `verdad-2026-09.sql`, `src/tools/catalogQuery.ts`, editor del panel, `src/owner/inventario.ts` (stock por Telegram) | Consola del dueño por Telegram (`src/owner/*`), seguimiento (`src/followup/*`), analista e insights, flywheel, panel (salvo Catálogo), medios (`src/media/*`), base de conocimiento (`src/kb/*`), legal (`src/legal.ts`), CLI y skills |
| `src/tools/cotizarEnvio.ts` + `member/zonas-envio.ts` | |
| Textos en femenino («clienta»), «$5 de abono», «cajas» dentro de descripciones de herramientas y seguimientos | |
| `docs/PLAN_CATALOGO_BABY_CALEB.md`, `docs/kb-panel-2026-08/` | `docs/plan-whatsapp-qr.md`, `docs/bitacora-whatsapp-qr.md`, `docs/FUENTES_DE_VERDAD.md` (lecciones que aplican tal cual) |

En D'CASA el catálogo, el stock, los precios, los combos y los Socios **ya viven en Odoo**: la
mitad izquierda de la tabla no se porta, se sustituye por Odoo (sección 3).

### 1.13 Lecciones que ya pagaron y que aplican a Juan

- Un dato, un solo dueño: el precio nunca va en el prompt ni en la base de conocimiento.
- El bot se calla cuando una persona contesta (desde el panel, el teléfono o Telegram), y lo
  comprueba tres veces (al llegar, al vencer el buffer, antes de enviar).
- Un archivo entrante (foto, comprobante) lo ve una persona, no la IA.
- Cuando toca escalar, se escala con una herramienta que avisa a alguien; «te paso el número»
  no es escalar (un pedido de 70 cajas se perdió así).
- El campo «instrucciones personalizadas» reemplazó el prompt entero por una línea: hoy se suma,
  no reemplaza.
- Una prueba que pasa dice que la señal elegida salió verde, no que el sistema funcione.

---

## 2. Riesgos honestos: QR (no oficial) frente a la API oficial

### 2.1 WhatsApp por QR (Baileys)

- **Es un cliente no oficial** que imita WhatsApp Web. Las condiciones de WhatsApp prohíben usar
  aplicaciones no oficiales o vincular la cuenta a versiones no oficiales; la consecuencia es
  la suspensión o el **bloqueo permanente del número, sin apelación efectiva** (SEGÚN FUENTE:
  guías 2025–2026 y el propio hilo de incidencias de Baileys «Repeated Number Bans»,
  `github.com/WhiskeySockets/Baileys/issues/2075`). Cifras de terceros hablan de bloqueos en
  semanas o de «uno de cada cinco al año» (NO VERIFICADO; son estimaciones de vendedores de la
  API oficial, con interés).
- **El propio CRM lo dice en tres sitios**: «Es un canal alterno — no es la API oficial y
  WhatsApp puede banear el número, así que la Cloud API se queda conectada» (`CLAUDE.md`,
  `docs/conectar-whatsapp-qr.md`, `src/channels/whatsappQr.ts:12-15`).
- **En D'CASA el número es el canal de ventas** (+507 6026-1919, en los botones del sitio y en
  la política de privacidad; `addons/website_dcasa/models/website.py:112-118`). Perderlo no es
  perder un bot: es perder el teléfono de la tienda. En Baby Caleb el QR está sobre el número
  del negocio también, y decidieron asumirlo; es una decisión de la dueña, no técnica.
- **Lo que ya les pasó** (`docs/bitacora-whatsapp-qr.md`): credenciales perdidas el 16-sep
  (hipótesis: 89 reconexiones en 2,5 h; hubo que re-escanear), una noche muda, el bot
  contestando encima de la dueña, conversaciones fantasma por estados, pre-keys que se
  acumulan y se podan a mano. Todo resuelto, pero muestra la fragilidad: **WhatsApp cambia el
  protocolo sin avisar** (migración a identificadores LID, formatos nuevos de chat) y Baileys
  corre detrás.
- **Operación**: exige un contenedor encendido 24/7, un Durable Object vivo, un cron por
  minuto y vigilancia cada 30 s; sin terminal el diagnóstico es por Actions. Es más de lo que
  tiene hoy nuestro Odoo (que duerme a los 30 min).
- **Lo que gana**: sin trámite con Meta, sin plantillas, sin ventana de 24 h (puede escribir
  primero a cualquiera), sin costo por mensaje, el teléfono sigue funcionando normal, lee y
  escribe en el chat que ya existe.

### 2.2 API oficial (WhatsApp Cloud API de Meta)

- **Precio** (SEGÚN FUENTE; `developers.facebook.com/documentation/business-messaging/whatsapp/pricing`
  bloqueado en esta sesión; resúmenes de Blueticks, Flowcall, Ominiflow, Wappbiz): desde el
  **1 de julio de 2025 se cobra por mensaje de plantilla** entregado, por categoría y país del
  cliente; **los mensajes de servicio (responder al cliente dentro de las 24 h de su último
  mensaje) son gratis**. Panamá cae en el bloque **«Rest of Latin America»**: marketing
  ≈ **$0.0740**, utilidad y autenticación ≈ **$0.0113** por mensaje; otra fuente cita
  $0.0851 / $0.0130 para un tarifario posterior. **Meta actualiza el tarifario cada trimestre**:
  la cifra exacta hay que leerla en su página el día de la decisión (NO VERIFICADO de primera
  mano).
- **Ventana de 24 h**: dentro, texto libre e imágenes; fuera, solo **plantillas aprobadas**
  (utilidad: «tu cotización está lista»; marketing: «Black Weekend»). Afecta a los seguimientos
  del CRM (ya lo contemplan, `src/followup/run.ts:33-37`).
- **Verificación del negocio**: sin verificar, el negocio queda en **250 conversaciones
  iniciadas por el negocio por 24 h** y sin nombre público aprobado; verificado (documentos
  del RUC, aviso de operación, sitio web con los datos) sube a 1.000/10.000/100.000 según
  calidad (SEGÚN FUENTE: Webex Connect, Clickatell, Wassenger). Para **responder** a clientes
  que escriben no hay límite por verificación.
- **El número actual: ¿puede migrar o coexistir?** Meta ofrece **«coexistencia»** («API
  Solutions for Business App Users»): el mismo número en la app **WhatsApp Business** del
  teléfono **y** en la Cloud API, con sincronización de contactos y de los chats de los últimos
  6 meses; las vendedoras siguen contestando desde el teléfono y el bot desde la API. Reglas
  (SEGÚN FUENTE: YCloud, Sleekflow, Chakra, Instantreply, Jalpi): el número debe estar en la app
  **Business** (no en WhatsApp normal) y no haber estado antes en la API; se vincula con un
  QR/código desde *Embedded Signup* de un proveedor; **hay que abrir la app en el teléfono al
  menos cada 14 días** o se pausa el enlace; tope de 20 mensajes/segundo; no sincroniza grupos,
  mensajes temporales ni de ver una vez; no disponible en Nigeria y Sudáfrica (Panamá sí). Sin
  coexistencia, la alternativa clásica es **migrar**: borrar el número de la app y registrarlo
  en la API (se pierde la app en el teléfono y el historial no pasa).
- **Política de IA (15 de enero de 2026)**: Meta prohíbe en la API los **asistentes de IA de
  propósito general** (ChatGPT, Perplexity…) como producto principal; **un bot de atención
  acotado a los productos de un negocio sigue permitido** (SEGÚN FUENTE: TechCrunch 18-oct-2025,
  Dataslayer, Galantis, Replypop). Juan es exactamente eso: hay que mantenerlo acotado a D'CASA
  y con **vía clara a una persona**, que la política de mensajería sí exige (SEGÚN FUENTE:
  Upperfloor, Keybe). Verificar la cláusula exacta en *WhatsApp Business Solution Terms* el día
  de la decisión.
- **Lo que gana**: número a salvo, soporte y estabilidad, webhooks (no hace falta contenedor),
  imágenes y documentos por API, plantillas con botones, verificación verde, métricas.
  **Lo que pierde**: trámite con Meta (días o semanas), plantillas para escribir primero,
  costo por mensaje iniciado, y **Meta ve que la atención es automatizada** (es lo correcto).

### 2.3 Comparación

| | QR (Baileys) | Cloud API (Meta) |
|---|---|---|
| Legalidad / términos | Viola los términos; riesgo de bloqueo del número | Oficial |
| Trámite | Escanear un QR | Meta Business + verificación + app + número |
| Costo WhatsApp | $0 | $0 respuestas; ≈ $0.011–0.085 por plantilla |
| Infra | Contenedor 24/7 + DO + cron (≈ $2/mes) | Solo Worker |
| Escribir primero / después de 24 h | Libre | Plantilla aprobada |
| Imágenes / PDF | Posible (hoy no implementado) | Posible (hoy no implementado) |
| Teléfono de las vendedoras | Sigue igual (y el bot ve lo que ellas escriben) | Con coexistencia, sigue igual |
| Estabilidad | Depende de que WhatsApp no cambie el protocolo | Estable, versionada |
| Quién asume el riesgo | D'CASA, con el número de ventas | — |

**Veredicto**: para el número de ventas de D'CASA, **Cloud API con coexistencia**. El QR puede
quedar como **respaldo opcional sobre un segundo número** (una línea nueva barata) o como canal
de pruebas, nunca sobre +507 6026-1919.

---

## 3. Opciones de integración con nuestro Odoo

### 3.0 Lo que Odoo ya tiene y Juan necesita (VERIFICADO-CÓDIGO)

- **Catálogo con todo lo público**: `addons/dcasa_tienda_borde` expone `GET /dcasa/tienda/feed`
  (protegido por `TIENDA_FEED_TOKEN`, bloqueado desde internet, solo lo pide el Worker) con, por
  producto: nombre, código, URL, precio, `mas_itbms`, categorías, descripción, **imagen y
  galería**, variantes, **combo** (`{texto, precio}`), modo de compra, `disponible` /
  `existencias`, enlace de WhatsApp, Black Weekend (`edge/src/tienda/tipos.ts:29-110`,
  `addons/dcasa_tienda_borde/models/website.py:62-70`). Se regenera solo cuando cambia precio,
  stock, publicación o una venta se confirma (`models/marcas.py`). **Es la fuente ideal para que
  Juan consulte el catálogo sin despertar a Odoo**, con la misma verdad que la tienda.
- **Reglas de Socios** en `addons/dcasa_socios/data/puntos.json` (1 punto por dólar pagado con
  ITBMS; 100 puntos = $1; compra mínima $20; referido 500/250 con la primera compra; canje mínimo
  500; código vigente 72 h; cumpleaños 500; no vencen); saldo = suma de `dcasa.movimiento`
  (`partner.dcasa_saldo`); llave = celular (`docs/SOCIOS.md`).
- **CRM de Odoo** instalado (`dcasa_base` depende de `crm`) y decisión de la dueña de construir
  encima (`docs/auditoria/BITACORA.md`: «el CRM se queda»; «Brian como parte del CRM mejorado:
  crear oportunidades desde WhatsApp/Telegram/chat»).
- **Brian** (`addons/dcasa_brian`): proveedores de IA (Anthropic por defecto `claude-sonnet-5-5`,
  OpenAI-compatibles, `prueba`), registro de herramientas con niveles y `grupos`, política dura
  (`politica.py`), auditoría `brian.accion`, Telegram vinculado por código, servidor MCP en
  `POST /brian/mcp` con clave de API de Odoo, **las sensibles nunca se ejecutan desde MCP**.
- **Borde**: `/jsonrpc`, `/xmlrpc`, `/json/2`, `/doc-bearer` y el feed están **bloqueados desde
  internet** (`edge/src/routing.ts:28`); `/brian/mcp` queda abierto con clave.
- **Odoo duerme** tras 30 min sin tráfico y el cron del Worker lo despierta cada hora
  (`docs/OPERACION.md`, `edge/wrangler.jsonc:47`). Una pregunta de un cliente a las 2 a.m.
  encontraría a Odoo dormido (~10 s de arranque caliente; hasta 7 min tras un despliegue).
- **Odoo Community no trae el módulo `whatsapp`** (es de Enterprise). El submódulo `vendor/odoo`
  no está inicializado en este worktree: por confirmar con `ls vendor/odoo/addons | grep whatsapp`.
- **Imágenes**: los adjuntos viven en R2 (`dcasa_adjuntos_r2`) y Odoo sirve las fotos de los
  productos publicados en URLs públicas que el borde cachea; el feed las trae ya resueltas.

### 3.1 Herramientas de Brian: cuáles servirían a un bot de clientes y cuáles jamás

Brian tiene 48 herramientas (`addons/dcasa_brian/models/herramientas_*.py`). Para Juan:

| Veredicto | Herramientas | Por qué |
|---|---|---|
| **Reutilizables con «vista pública»** | `buscar_productos`, `ver_producto`, `listar_categorias` | Hoy devuelven **existencias exactas y por almacén**, filtran por `sale_ok` (no por publicado) y muestran categorías internas (`herramientas_catalogo.py:46-80`). Para un cliente hay que devolver «disponible / pocas / agotado», solo publicados, precio «+ ITBMS», combo, medidas y foto. Mejor aún: leer el **feed** (3.0). |
| **Reutilizable con candado** | `saldo_puntos` | Solo si el celular de WhatsApp es el de la ficha, y conviene pedir el PIN del socio antes de mostrar el saldo (el programa ya tiene celular + PIN). Sin los «últimos movimientos» con motivos. |
| **Nuevas, de lectura** | `reglas_socios` (lee `puntos.json`), `horario_y_tienda`, `catalogo_publico` (feed) | Para que ninguna cifra salga de la memoria del modelo. |
| **Nuevas, de escritura acotada** | `crear_oportunidad` (`crm.lead` con el resumen y el celular), `anotar_conversacion` (nota en el chatter de `res.partner`), `pasar_a_vendedora` (actividad + aviso), `crear_cliente` (ya existe: celular como llave, no duplica) | Lo mínimo para que la venta no se pierda y quede en Odoo. |
| **Jamás** | `ajustar_puntos`, `confirmar_venta`, `cancelar_cotizacion`, `crear_factura`, `editar_factura`, `publicar_factura`, `registrar_pago`, `conciliar_movimiento`, `crear_producto`, `actualizar_producto`, `publicar_producto_web`, `ajustar_existencias`, `proponer/aplicar/deshacer_importacion`, `crear/desactivar_usuario`, `cambiar_rol_usuario` | Escriben dinero, stock, precios o permisos. |
| **Jamás (datos internos o de terceros)** | `reporte_del_dia`, `resumen_ventas`, `buscar_ventas`, `ver_venta`, `reporte_contable`, `facturas_pendientes`, `ver_factura`, `clientes_que_deben`, `existencias_bajas`, `buscar_clientes`, `ver_cliente`, `listar_usuarios`, `movimientos_por_conciliar`, `guia_cierre_mes`, `pantalla_actual`, `abrir`, `buscar_en_todo`, `ayuda` | Un cliente nunca debe ver ventas, deudas ni fichas de otros. |
| **Discutible** | `crear_cotizacion` + `agregar_linea_cotizacion` | Podría dejar una cotización borrador para la vendedora; prefiero `crear_oportunidad` y que la vendedora cotice (regla 4: no prometer). |

Las reglas de Socios que Juan hereda sin discusión: **no existe columna de saldo** (lee
`dcasa_saldo`), **el libro no se edita** (`politica.py` `proteger_libro_puntos`), **ninguna
cifra fuera de `puntos.json`**, **el referido se paga con la primera compra** (Juan puede
explicar el programa y dar el enlace `/r/CÓDIGO`, nunca «acreditar»).

Cómo se acota en Brian: el decorador `@herramienta` filtra por `grupos`; un **usuario técnico
`juan`** con un grupo propio (`dcasa_brian.group_juan`) y **sin** los grupos internos vería
solo las herramientas registradas con ese grupo, y las sensibles ya no se ejecutan desde MCP
(`docs/BRIAN.md`). Todo queda auditado en `brian.accion` (quién, canal, argumentos, resultado).

### 3.2 Opción A — Correr el CRM tal cual (dos Workers aparte) y conectarlo a Odoo

- **Cómo**: desplegar `juancitoads-bot` + `juancitoads-bot-wa` con nuevos nombres en nuestra
  cuenta; reemplazar `catalogQuery` por una llamada a Odoo (MCP de Brian con usuario `juan`, o
  el feed), y `captureLead`/`handoffHuman` por escrituras en Odoo (oportunidad, nota). JSON-RPC
  con usuario técnico **no**: está bloqueado en el borde a propósito (`routing.ts:28`) y abrirlo
  es abrir el servicio `db`.
- **Esfuerzo**: **S–M** (1–2 semanas). Casi todo es configuración y dos herramientas.
- **Pros**: lo más rápido; se hereda todo (panel, consola, seguimiento, insights).
- **Contras**: **no «vive dentro de Odoo»**: dos bandejas (panel `/admin` y Odoo), dos lugares
  con conversaciones, leads y tickets duplicados, una contraseña única compartida para el panel,
  dos bases de conocimiento, la marca de Juancito Ads en el panel; mantenimiento de un segundo
  producto entero (~21.000 líneas) con todo lo que no usaremos (Cal.com, ManyChat, Twilio,
  campañas, niche packs, CLI). Es la trampa que su propio `FUENTES_DE_VERDAD.md` describe: dos
  dueños del mismo dato.

### 3.3 Opción B — Portar el CRM a un módulo de Odoo (`dcasa_juan`) y dejar fuera solo el puente

- **Cómo**: nuevo módulo que reciba los webhooks de la Cloud API (y del puente) en Odoo,
  reutilice `brian.conversacion` con un canal `whatsapp` y el bucle de `proveedores.py`, guarde
  cada mensaje en el chatter del cliente (`mail.message` en `res.partner`), cree `crm.lead`,
  deje que la vendedora conteste desde Odoo (Discuss/chatter) y exponga las herramientas de Juan
  con el ORM bajo el usuario `juan`. El puente (Container) sigue en Cloudflare porque Odoo no
  puede sostener un WebSocket con WhatsApp.
- **Esfuerzo**: **L** (6–10 semanas): hay que reescribir en Python el buffer de 15 s (en Odoo
  sería un cron o un hilo), el takeover, la gestión de medios (Odoo → R2), la transcripción
  (Whisper vía Workers AI desde Odoo o proveedor aparte), el seguimiento, el anti-spam, el tope
  de presupuesto, la vista de bandeja, y pruebas de todo. Sin RAG (Vectorize): la base de
  conocimiento serían páginas/FAQ en Odoo (suficiente para muebles; no hace falta vectores).
- **Pros**: un solo sistema, un solo login, una sola fuente de verdad, chatter y CRM nativos,
  Brian y Juan con el mismo registro de herramientas y la misma auditoría; todo en nuestro
  repo, con nuestras reglas y nuestros tests.
- **Contras**: **Odoo es la tienda y la contabilidad**: cada mensaje de WhatsApp despertaría y
  cargaría la misma instancia única `basic` (1/4 vCPU, 1 GiB; PSS medido ≈ 660 MiB bajo 40
  peticiones; `docs/auditoria/BITACORA.md`); un cliente que escriba a las 2 a.m. espera el
  arranque; una ráfaga de spam compite con la caja. Tiempo largo antes de ver algo funcionando
  y se tira lo que ya funciona (903 pruebas). Odoo Community no trae módulo de WhatsApp.

### 3.4 Opción C — Híbrido: puente + motor de IA en el Worker, Odoo única fuente de datos y bandeja

- **Cómo**:
  1. Un Worker **`juan`** en nuestra cuenta, derivado del CRM **recortado**: motor
     (`agent.ts`, takeover, medios, anti-spam, presupuesto, prompt con `<fuentes_de_verdad>`,
     seguimiento), canales **Cloud API** (principal) y **QR** (opcional, otro número), consola
     de Telegram para avisos. Se eliminan catálogo en D1, leads/tickets como dueños del dato,
     Twilio/ManyChat/Cal.com/campañas/niches/CLI, y la carpeta `member/` se sustituye por la
     configuración de D'CASA en nuestro repo (voz de `CLAUDE.md`).
  2. **Odoo es la única verdad**: Juan lee el catálogo del **feed** (mismo JSON que la tienda;
     rápido, no despierta a Odoo) y, cuando necesita algo vivo o escribe, llama al **MCP de
     Brian** con el usuario `juan` (herramientas de 3.1). D1 queda solo como memoria operativa
     del bot (buffer, estado de conversación, caché del feed, media temporal).
  3. **Bandeja en Odoo**: cada conversación se anota en el chatter del cliente (celular como
     llave; crea la ficha si no existe) y cada interés se vuelve **oportunidad en CRM**; la
     vendedora toma la conversación desde Odoo (botón «Atender por WhatsApp» que avisa al
     Worker y pausa a Juan) o desde Telegram (vínculo que Brian ya tiene). Lo que la vendedora
     escribe desde el teléfono también pausa a Juan (coexistencia + reglas de takeover).
  4. Un **endpoint interno** `juan` → Odoo por service binding al Worker `dcasa` (ya está delante
     del contenedor), nunca por internet; y Odoo → `juan` con un token para «enviar por
     WhatsApp» (cotización en PDF, foto de producto).
- **Esfuerzo**: **M** (4–6 semanas de trabajo, en fases; algo útil en 2–3).
- **Pros**: reutiliza lo probado (el puente tal cual, el motor y sus pruebas), datos en Odoo
  sin duplicados, Odoo no carga con el tráfico de WhatsApp ni con los bucles de IA, el bot vive
  despierto aunque Odoo duerma (contesta con el feed y encola la escritura), costo bajo, y queda
  un camino abierto a la opción B si algún día se quiere todo en Python.
- **Contras**: dos bases de código (Worker TypeScript + Odoo Python) que ya tenemos de todos
  modos (`edge/`); hay que escribir las herramientas de Juan en Brian y recortar el CRM con
  cuidado (sus tests de Baby Caleb se reemplazan por los nuestros).

### 3.5 Recomendación: **C**, con Cloud API en coexistencia como canal principal

| Criterio | A | B | C |
|---|---|---|---|
| Costo mensual adicional (sección 5) | ≈ $10–40 | ≈ $8–31 (IA) + más CPU de Odoo (quizá subir de `basic`: +$20) | ≈ $10–40 |
| Mantenimiento | Dos productos completos | Un producto, pero reescrito | Un Worker recortado + Brian |
| Riesgo | Datos duplicados, panel aparte, marca ajena | Carga y disponibilidad del ERP; tiempo largo | Bajo: lo nuevo son herramientas de lectura y una bandeja |
| Tiempo a algo usable | 1–2 semanas | 6–10 semanas | 2–3 semanas (prueba cerrada) |
| «Vive dentro de Odoo» | No | Sí | Datos y bandeja sí; motor no |

Justificación corta: C respeta las dos cosas que la dueña pidió —**que funcione como ya
funciona** y **que la verdad sea la de D'CASA**— sin cargar la tienda con un bot ni
mantener dos CRM. B es el destino natural si en seis meses Juan demuestra valor y queremos
una sola pila; C deja ese camino abierto.

### 3.6 Arquitectura propuesta (C)

```
Cliente ──WhatsApp (Cloud API, coexistencia)──▶ Worker "juan" ──┐
        ◀─────────────────────────────────────  (motor del CRM)  │ service binding
Vendedora ─app WhatsApp del teléfono (mismo número)─────────────┼──▶ Worker "dcasa" ──▶ Odoo
                                                                 │    · /brian/mcp (usuario juan)
Telegram (avisos, vínculo de Brian) ◀──────────── juan ─────────┘    · feed del catálogo (KV)
                                                                      · chatter + crm.lead
Odoo ──"enviar por WhatsApp" (cotización PDF, foto)──token──▶ juan ──▶ Cloud API
[opcional] puente QR (Container lite) sobre un 2.º número ──▶ juan
```

---

## 4. Lo que faltaría en cualquier caso

### 4.1 Enviar imágenes y archivos (lo que la dueña ya echó en falta)

- **Hoy ninguno de los dos canales envía medios** (VERIFICADO-CÓDIGO): el puente solo acepta
  `{ para, chunks: [texto] }` y llama `sendMessage(jid, { text })`
  (`puente-wa/contenedor/servidor.mjs:685-700`); el adaptador oficial solo manda `type: "text"`
  (`src/channels/whatsapp.ts:191-215`). El panel y la consola tampoco adjuntan.
- **Qué hace falta**: en la Cloud API, mensajes `type: "image"` / `type: "document"` con una URL
  pública (la foto del producto ya es pública desde Odoo/borde; la cotización PDF se puede
  publicar con URL firmada y vencimiento) o subida previa a `/media` (SEGÚN FUENTE: referencia
  de la Cloud API; verificar formato exacto al implementar). En Baileys,
  `sendMessage(jid, { image: { url }, caption })` y `{ document: { url }, fileName, mimetype }`
  (NO VERIFICADO en código; es la API documentada de la librería). Trabajo **S** por canal más
  una herramienta de Juan `enviar_foto_producto` que use la imagen del feed, y un botón en
  Odoo «Enviar cotización por WhatsApp» que ya existe como enlace `wa.me`
  (`herramientas_ventas.py:248-262`) y pasaría a enviar el PDF de verdad.
- **Recibir** ya está: fotos y notas de voz entran por los dos canales; en D'CASA una foto de
  comprobante debe seguir la regla del CRM (no la ve la IA; la ve una vendedora).

### 4.2 Traspaso a una vendedora

- El CRM ya tiene el mecanismo (`src/takeover.ts`): tres puertas (panel, teléfono, Telegram),
  pausa configurable (5 min a 7 días), devolver al bot con nota, cierre de tickets. En C, las
  puertas pasan a ser **Odoo** (chatter/oportunidad con «Atender»), **el teléfono** (con
  coexistencia, lo que escriba la vendedora desde la app es visible para la API y pausa a Juan)
  y **Telegram** (vínculo por código que Brian ya tiene; `docs/BRIAN.md` «Telegram»).
- Horario de atención humana: fuera de horario Juan atiende y anota «te confirmo mañana a
  primera hora»; dentro, crea la oportunidad y avisa; nunca «te paso el número y listo».
- WhatsApp exige una **vía clara a una persona** (2.2): la frase «escríbeme *persona* y te
  atiende una vendedora» cumple y es fácil de probar.

### 4.3 Horario

Juan contesta 24/7 (es su gracia) pero **promete entregas y visitas solo en horario**: lo lee de
una herramienta `horario_y_tienda` (Odoo: `resource.calendar` de la empresa o un parámetro de
`website_dcasa`), con la fecha y hora de Panamá en el prompt (como Brian).

### 4.4 Voz de marca

El CRM lo resuelve por configuración: `formaDeTrato: "tu"` (nuestra regla 6: tuteo; Baby
Caleb usa usted), `<business_context>` corto con los datos reales de la empresa
(`CLAUDE.md` «Datos reales»), `tone` «el pana que sabe de casas», y una lista de palabras
prohibidas («remate», «¡¡CORRE!!», emojis) en los anti-patrones. El CTA único sigue siendo
WhatsApp: Juan **es** el WhatsApp, así que su CTA es «¿quieres que una vendedora te
confirme?». Las pruebas de `test/babycaleb/trato-y-busqueda.test.ts` se reescriben como
`test/dcasa/voz.test.ts` con nuestras reglas.

### 4.5 No inventar precios ni promesas

Se hereda el bloque `<fuentes_de_verdad>` apuntando a las herramientas de Juan: precio solo del
feed/Odoo y **siempre con la leyenda «+ ITBMS»** (decisión del dueño, `BITACORA.md`); «si no
aparece, no lo manejamos»; existencias como etiqueta, nunca el número (el feed trae
`existencias`; la herramienta de Juan la convierte); entregas, financiamiento y apartados
**siempre «te lo confirma una vendedora»** (el apartado exige ser Socio y sus reglas están
pendientes, `docs/auditoria/ronda5/pagos-y-apartados.md`); descuentos: ninguno por su cuenta.
Las mismas pruebas que el CRM usa contra «precios en el prompt» se mantienen.

### 4.6 Socios D'CASA

Juan explica el programa con cifras de `puntos.json` (herramienta, no memoria), da el enlace de
referido del socio que lo pide (`/r/CÓDIGO`) y muestra el saldo solo tras PIN. **Nunca** escribe
en `dcasa.movimiento`, nunca «acredita», nunca promete puntos de una compra no facturada
(los puntos nacen con la factura pagada, `docs/SOCIOS.md`).

### 4.7 Privacidad y legal (Ley 81 de 2019)

- Nuestra política (`addons/website_dcasa/views/legal_templates.xml:55-73`) describe a Brian
  como asistente **interno** y nombra a Meta (Muse Spark) y Anthropic como proveedores de IA, y
  a WhatsApp «cuando nos escribes por ahí». Para Juan hay que **añadir**: que la atención por
  WhatsApp es **automatizada con IA** y se puede pedir una persona; que la conversación se
  envía al proveedor de IA para responder; cuánto tiempo se guarda (en Odoo, en el chatter,
  mientras sea cliente; en el Worker, días); el derecho a borrado; y que WhatsApp/Meta procesan
  el mensaje además por su cuenta.
- Primer mensaje de Juan: se presenta como asistente automático de D'CASA (principio 7 del
  CRM; en varias plataformas es obligatorio) con la vía a una persona.
- Meta exige páginas públicas de privacidad, términos y borrado de datos para aprobar la app:
  las nuestras ya existen en el sitio (`/privacidad` y relacionadas en `website_dcasa`).
- Un comprobante de pago o un documento de identidad que mande un cliente **no se le muestra a
  la IA**: se adjunta al chatter y lo revisa una vendedora.

### 4.8 Operación

Odoo dormido (3.0) → Juan responde con el feed y encola las escrituras; tiempo de espera del
Worker hacia Odoo ≥ 60 s con reintento; límite por número (el anti-spam del CRM) y tope de
presupuesto mensual obligatorio (ronda 4 ya pidió tope para Brian, hoy sin tope: aplica a Juan
igual). Un `/dcasa/salud` para Juan como el de Odoo.

---

## 5. Costos (ESTIMACIÓN, con fuentes)

| Concepto | Costo/mes | Fuente |
|---|---|---|
| Plan Workers Paid | $5, **ya pagado** por producción | `docs/OPERACION.md` «Cuánto cuesta» |
| Worker `juan` + Durable Objects + D1 + KV | ≈ $0 dentro de lo incluido (D1: 25 mil millones de lecturas y 50 M escrituras/mes incluidas; Vectorize 50 M dimensiones consultadas incluidas si se usara) | `developers.cloudflare.com/workers/platform/pricing/` (MCP de Cloudflare, 2026-10-02) |
| Workers AI (Whisper para notas de voz) | 10.000 neuronas/día incluidas; después $0.011 por 1.000 | `developers.cloudflare.com/workers-ai/platform/pricing/`. Cuántas neuronas cuesta un audio: NO VERIFICADO; cientos de audios al mes deberían caber |
| Puente QR, contenedor `lite` 24/7 (**solo si se usa**) | ≈ $1.75–2.00: memoria 256 MiB × 730 h − 25 GiB-h incluidas ≈ $1.42; disco 2 GB ≈ $0.32; CPU 1/16 vCPU por uso real, centavos | `developers.cloudflare.com/containers/platform/pricing/` ($0.0000025/GiB-s, $0.00000007/GB-s, $0.00002/vCPU-s); coincide con lo medido por el CRM |
| WhatsApp Cloud API | $0 por respuestas dentro de 24 h; seguimientos/avisos con plantilla ≈ $0.0113 (utilidad) a $0.0740 (marketing) cada uno; 200 plantillas/mes ≈ $2–15 | SEGÚN FUENTE (2.2); leer el tarifario de Meta el día de la decisión |
| IA (supuesto: 400 conversaciones/mes × 6 turnos × 2 llamadas; 2.500 tokens de entrada por llamada, 2.000 de ellos cacheados; 200 de salida) | **Haiku 4.5 ≈ $8** · **Sonnet 5.5 ≈ $16** · **Opus 5.5 ≈ $31** | Tarifas Anthropic cargadas en esta sesión: Haiku $1/$5, Sonnet 5.5 $2/$10, Opus 5.5 $4/$20 por millón; lectura de caché a $0.20 (Sonnet/Opus) y ≈ 10 % (Haiku, NO VERIFICADO). El doble de conversaciones = el doble de costo |
| Verificación de Meta | $0 | — |
| Segundo número (si se quiere QR de respaldo) | lo que cueste la línea | — |

**Total adicional estimado: ≈ $10–40/mes.** Con tope de presupuesto en el bot (hereda el
`monthly_budget` del CRM) el techo lo pone la dueña.

Comparación con B: lo mismo en IA, pero Odoo despierto 24/7 (ya se asume en los ≈ $12) y
probablemente subir de `basic` a `standard-1` para aguantar bot + tienda + caja: de ≈ $13 a
≈ $34/mes (`docs/auditoria/ronda4/costos-y-limpieza.md`).

---

## Decisiones de la dueña (2026-10-02, tras leer este informe)

1. **Canal: WhatsApp por QR, sabiendo el riesgo.** La dueña conoce que Meta no lo aprueba y
   decide mantenerlo (es como funciona su CRM de Baby Caleb). Mitigaciones obligatorias: ritmo de
   envío conservador (el CRM ya lo trae), seguimientos limitados (abajo), copia diaria de la
   sesión, y el adaptador de la API oficial listo como plan B si bloquean el número.
   **Número del QR: lo decide la dueña cuando el sistema esté terminado** (2026-10-03).
2. **Nombre público: «el equipo de D'CASA»**, no «Juan». («Juan» queda solo como nombre interno
   del proyecto.)
3. **Atiende 24/7.**
4. **Seguimiento a quien preguntó y no volvió a escribir**: como máximo DOS mensajes:
   - el primero **5 horas** después del último mensaje, **solo dentro del horario laboral** (si
     cae fuera, espera al siguiente horario laboral);
   - el segundo, si sigue sin responder, **5 días** después;
   - **ninguno si ya compró**. Nada más: la dueña no quiere «tanto seguimiento».
   **Horario laboral (dueña, 2026-10-03): de 8:00 a. m. a 5:00 p. m., todos los días (hora de Panamá).**

## 6. Plan por fases y lo que necesito que la dueña decida o provea

### Fase 0 — Decisiones (1 semana, sin código)

| # | Decisión / cosa que proveer | Por qué |
|---|---|---|
| 1 | **¿+507 6026-1919 está en la app WhatsApp Business o en WhatsApp normal?** Si es normal, migrarlo a Business (gratis, mismo número) **antes** de nada | La coexistencia solo funciona con la app Business |
| 2 | **Cuenta de Meta Business** (business.facebook.com) a nombre de D'CASA Panamá, con **verificación de negocio**: RUC 155779346-2-2026 DV7, aviso de operación, dirección Frente al Parque Libertadores, diagonal a la Discoteca Seven, La Chorrera, Panamá Oeste, sitio dcasapty.com con esos datos visibles | Sin verificar: 250 conversaciones iniciadas/día y sin nombre público; la verificación tarda días |
| 3 | **Quién es administrador** de ese Meta Business y de la app (correo de la dueña + uno técnico) | Los tokens salen de ahí; nunca se pegan en chats |
| 4 | **Nombre público del bot** («Juan, asistente de D'CASA» o solo «D'CASA») y confirmación de que se presenta como automático | Obligación de honestidad; política de Meta |
| 5 | **Modelo y presupuesto de IA**: arrancar con Haiku 4.5 (≈ $8/mes) y subir a Sonnet 5.5 si la calidad lo pide; **tope mensual** (p. ej. $30) | El tope evita sustos; el CRM baja de modelo solo, nunca se calla |
| 6 | **Horario de atención humana** y **quién atiende** (vendedoras con Telegram vinculado y/o Odoo) | Define el traspaso y lo que Juan promete |
| 7 | **¿QR como respaldo?** Si sí, **un segundo número** (nunca el de ventas) | Riesgo de bloqueo |
| 8 | Aprobar el **texto de privacidad** actualizado (4.7) y el **primer mensaje** de Juan | Ley 81 y Meta |
| 9 | Confirmar que Juan **no** cotiza entregas, financiamiento ni apartados: siempre «te lo confirma una vendedora» | Regla 4 y pendientes de la ronda 5 |

### Fase 1 — Prueba cerrada (2–3 semanas de trabajo; sin tocar el número real)

- Worker `juan` en nuestro repo, derivado del CRM recortado (3.4), con nuestras pruebas.
- Herramientas de Juan en Brian (3.1) + usuario `juan` + grupo propio; herramienta de catálogo
  sobre el feed; `crear_oportunidad` y `anotar_conversacion` en Odoo.
- Cloud API con el **número de prueba de Meta** (hasta 5 teléfonos verificados, gratis), igual
  que lo hizo Baby Caleb (`skill/references/channel-setup-guides/whatsapp-cloud.md`).
- Traspaso a vendedora por Telegram y desde Odoo; horario; voz de marca; envío de foto de
  producto.
- Criterio de salida: una vendedora y la dueña chatean con Juan una semana y ninguna respuesta
  inventa precio, promesa o producto; cada interés aparece como oportunidad en Odoo.

### Fase 2 — Piloto con el número real (2 semanas)

- Verificación de Meta aprobada → **coexistencia** del número (QR desde Embedded Signup de un
  proveedor o de Meta; SEGÚN FUENTE, verificar el camino sin intermediario) → Juan atiende
  solo fuera de horario o solo para «precios y disponibilidad» al principio.
- Cotización en PDF por WhatsApp desde Odoo; comprobantes al chatter sin pasar por la IA.
- Medir: costo real de IA, conversaciones, oportunidades creadas, traspasos, quejas.

### Fase 3 — Afinar (continuo)

- Seguimientos con plantillas de utilidad (costo por mensaje), saldo de Socios con PIN,
  analista nocturno sobre las conversaciones (en Odoo o en el Worker), retirar lo que quede del
  panel `/admin` a favor de Odoo; evaluar si conviene el paso a B.

---

## 7. Fuentes

Código (VERIFICADO-CÓDIGO):
`/home/user/juanarrietabusiness-pixel/crm-baby-caleb/` — `CLAUDE.md`, `README.md`, `EMPIEZA-AQUI.md`,
`PRIVACY.md`, `wrangler.toml`, `package.json`, `src/index.ts`, `src/agent.ts`,
`src/llm/provider.ts`, `src/pricing.ts`, `src/budget.ts`, `src/system-prompt.ts`,
`src/businessContext.ts`, `src/settings-loader.ts`, `src/tools/*.ts`, `src/db/schema.sql`,
`src/db/catalog.ts`, `src/channels/whatsapp.ts`, `src/channels/whatsappQr.ts`,
`src/replies/sender.ts`, `src/takeover.ts`, `src/media/*.ts`, `src/owner/*.ts`,
`src/followup/run.ts`, `src/kb/*.ts`, `src/legal.ts`, `member/*`, `puente-wa/wrangler.toml`,
`puente-wa/esquema.sql`, `puente-wa/src/worker.ts`, `puente-wa/src/comun.ts`,
`puente-wa/contenedor/{Dockerfile,servidor.mjs,propios.mjs,package.json}`,
`.github/workflows/*.yml`, `docs/plan-whatsapp-qr.md`, `docs/bitacora-whatsapp-qr.md`,
`docs/conectar-whatsapp-qr.md`, `docs/FUENTES_DE_VERDAD.md`, `docs/AUDITORIA_CONOCIMIENTO.md`,
`docs/consola-del-dueno.md`, `docs/PLAN_CATALOGO_BABY_CALEB.md`,
`skill/references/channel-setup-guides/*.md`.

Nuestro repo: `CLAUDE.md`, `docs/BRIAN.md`, `docs/ARQUITECTURA.md`, `docs/SOCIOS.md`,
`docs/OPERACION.md`, `docs/auditoria/BITACORA.md`, `docs/auditoria/ronda4/costos-y-limpieza.md`,
`docs/auditoria/ronda5/pagos-y-apartados.md`, `addons/dcasa_brian/models/{registro,politica,
herramientas_catalogo,herramientas_clientes,herramientas_ventas,proveedores,conversacion,telegram}.py`,
`addons/dcasa_brian/controllers/mcp.py`, `addons/dcasa_socios/data/puntos.json`,
`addons/dcasa_tienda_borde/{controllers/main.py,models/website.py,models/marcas.py}`,
`edge/src/tienda/tipos.ts`, `edge/src/routing.ts`, `edge/wrangler.jsonc`,
`edge/CONTRATO_CONTENEDOR.md`, `addons/website_dcasa/views/legal_templates.xml`,
`addons/website_dcasa/models/website.py`.

Externas (SEGÚN FUENTE, vía buscador; las páginas oficiales de Meta/WhatsApp estaban bloqueadas):
- Precio por mensaje y bloque «Rest of Latin America»: blueticks.co/blog/whatsapp-business-api-pricing-2026,
  flowcall.co/blog/whatsapp-business-api-pricing, ominiflow.com/whatsapp-api-pricing-by-country,
  wappbiz.com/blogs/whatsapp-business-latest-pricing-update, mobileecosystemforum.com (feb-2026).
  Oficial (no leída): developers.facebook.com/documentation/business-messaging/whatsapp/pricing.
- Coexistencia: ycloud.com/blog/whatsapp-business-app-coexistence-meta-update,
  sleekflow.io/en-us/blog/whatsapp-coexistence, chakrahq.com (FAQ), instantreply.co (qué sincroniza),
  docs.360dialog.com (onboarding). Oficial (no leída):
  developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users.
- Límites y verificación: help.webexconnect.io/docs/whatsapp-messaging-limits,
  clickatell.com (messaging limits), wassenger.com (sin verificación).
- Política de IA 15-ene-2026: techcrunch.com (2025-10-18), dataslayer.ai, whatsapp.galantis.com,
  replypop.com. Escalado a humano: upperfloor.ai, keybe.ai.
- Riesgo de Baileys: github.com/WhiskeySockets/Baileys/issues/2075, whatsapp.checkleaked.cc,
  blog.kraya-ai.com (cifras de terceros, NO VERIFICADAS).
- Cloudflare: developers.cloudflare.com/containers/platform/pricing/,
  developers.cloudflare.com/workers/platform/pricing/, developers.cloudflare.com/workers-ai/platform/pricing/
  (leídas por el MCP de Cloudflare el 2026-10-02).
- Anthropic: tabla de modelos y precios de la ficha `claude-api` cargada en esta sesión (2026-09-25).
