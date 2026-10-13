# El puente de WhatsApp de D'CASA (para Juan)

Esta guía es para la dueña. Está escrita sin tecnicismos; lo que es solo para quien opera el sistema va
al final, en el apéndice.

> **Estado:** el puente está construido y probado con un WhatsApp de mentira (un doble). **No se ha
> conectado a ningún WhatsApp real ni se ha desplegado.** Nada de esto se enciende hasta que tú lo decidas:
> el número lo eliges tú, al final.

---

## En una frase

El puente es el «teléfono» que sostiene WhatsApp las 24 horas para que el asistente («el equipo de D'CASA»)
pueda leer lo que escriben los clientes y contestarles, incluso con fotos y documentos. Funciona vinculando
un número **como si fuera WhatsApp Web** (por código QR).

## Lo importante antes de todo

1. **Es un camino no oficial.** WhatsApp (Meta) no lo aprueba y puede **bloquear el número** sin aviso y sin
   apelación. Tú lo decidiste sabiéndolo. Esta guía te dice cómo bajar ese riesgo (sección 6) y qué hacer si
   pasa (sección 7), pero **nadie puede garantizar que no te bloqueen**.
2. **Tu teléfono sigue funcionando igual.** Sigues leyendo y contestando desde el teléfono. Lo que tú
   escribes desde ahí el asistente lo nota y **se calla** en esa conversación (la toma una persona).
3. **Nunca pegues una contraseña o clave en un chat ni en GitHub.** Van solo en el panel de Cloudflare.

---

## 1. Qué necesitas tener listo

- La cuenta de Cloudflare de D'CASA (ya la usa la tienda).
- El **teléfono del negocio** con WhatsApp, con internet, en tus manos el día de vincular.
- Un gestor de contraseñas (para crear y guardar los dos secretos de abajo).
- Telegram, si quieres que el sistema te **avise** cuando WhatsApp se desconecte (recomendado).
- El Worker del asistente (`juan`) ya desplegado: el puente se conecta a él.

## 2. Poner los secretos (una sola vez)

Los secretos **no pasan por GitHub**: los pegas tú en Cloudflare, en el Worker del puente
(**dcasa-puente-wa**; el de pruebas se llama **dcasa-puente-wa-staging**):

> Cloudflare → Workers y Pages → **dcasa-puente-wa** → Configuración → **Variables y secretos** →
> Agregar → tipo **Secreto**.

| Nombre | Para qué sirve | Cómo es |
|---|---|---|
| `WA_TOKEN` | La contraseña que comparten el puente y el asistente (`juan`). | Generada por ti con tu gestor: **mínimo 24 caracteres, solo letras, números y guiones** (sin ñ, tildes ni símbolos raros). **El mismo valor** que en el Worker `juan`. |
| `WA_SESION_CLAVE` | Cierra con llave la sesión de WhatsApp guardada (nadie que vea la base de datos puede usarla). | Otra contraseña **distinta**, de **mínimo 32 caracteres**. **No se cambia nunca** una vez puesta (si se pierde o se cambia mal, hay que volver a escanear el QR). Guárdala en tu gestor. |
| `TELEGRAM_BOT_TOKEN_JUAN` | *(Opcional)* El bot de Telegram que te avisa. | El que te da BotFather. |
| `ALERTA_TELEGRAM_CHAT` | *(Opcional)* Tu chat de Telegram, a donde llegan los avisos. | El número de tu chat. |

Mientras falten los dos primeros, **el puente no hace nada peligroso**: no enciende el contenedor, no intenta
conectar WhatsApp y, si le preguntas cómo está, contesta «sin configurar» y **solo los nombres** de lo que
falta. Cuando los pones, empieza solo (en un minuto).

> Al desplegar nuevas versiones **nunca se borran** los secretos que pusiste en el panel.

## 3. Enlazar el número con el código QR

Hazlo **solo cuando hayas decidido el número** y con el asistente ya probado.

1. En el teléfono del negocio: **WhatsApp → Ajustes → Dispositivos vinculados → Vincular un dispositivo**.
2. Pide el código QR (en Odoo, cuando esa pantalla esté lista; mientras tanto lo pide quien opera, apéndice A).
3. Apunta la cámara del teléfono al código. **El código vence a los 45 segundos**: si el teléfono dice
   «Revisa tu conexión y vuelve a intentarlo», casi seguro el código ya estaba vencido; pide uno nuevo
   y escanea enseguida.
4. En unos segundos el estado pasa a **conectado**. Entonces en la lista de dispositivos del teléfono verás
   uno llamado **DCASA Panama**.
5. **La prueba que de verdad cuenta:** desde **otro** teléfono, escríbele al número. El asistente tiene que
   contestar. Pídele también una foto del catálogo: tiene que llegar la imagen. (Si solo miras que diga
   «conectado», puede pasar que el aparato haya quedado a medio instalar. Quien opera comprueba además que
   `instalacionCompleta` sea `true`, apéndice A.)

Una vez vinculado **no vuelve a pedir el código**, aunque se reinicie todo: la sesión queda guardada,
cifrada, dentro del propio sistema.

## 4. Cómo saber cómo está

El estado tiene cinco posibilidades:

| Estado | Qué significa | Qué haces |
|---|---|---|
| **conectado** | Todo bien. | Nada. |
| **necesita QR** | Nunca se vinculó, o se desvinculó desde el teléfono. | Escanear un código nuevo (sección 3). |
| **desconectado desde hace N min** | Estaba vinculado y se cayó la conexión. Se reintenta solo. | Esperar unos minutos; si pasa de 10, te llega el aviso de Telegram. |
| **apagado** | El interruptor `PUENTE_ACTIVO` no está en «on». | Solo si lo apagaste tú a propósito. |
| **sin configurar** | Faltan secretos (se listan por nombre). | Sección 2. |

## 5. Lo que el puente hace por ti

- **Responde con ritmo humano:** muestra «escribiendo…», marca el mensaje como leído, deja **al menos 1
  segundo entre burbujas** y un poco más al azar. No contesta nunca a grupos ni a estados.
- **Ignora lo viejo:** el historial que WhatsApp entrega al reconectar no se contesta.
- **Si Juan (el asistente) está caído un rato,** los mensajes de los clientes **no se pierden**: se guardan
  (cifrados, hasta 48 horas) y se entregan en cuanto vuelva.
- **Cuando escribes tú desde el teléfono,** el asistente se entera y deja de contestar esa conversación.
- **Copia de seguridad diaria** de la sesión (cifrada), 7 días.
- **Te avisa por Telegram** si WhatsApp lleva 10 minutos desconectado, y cuando vuelve.

## 6. Cómo bajar el riesgo de bloqueo

Lo que más delata a un bot no es lo que dice, sino **cómo** escribe. Ya está puesto:

- **Topes de envío** (se pueden bajar, no conviene subirlos): 10 mensajes por minuto, 400 por día, 30 por
  hora a una misma persona, y **15 personas nuevas por día** (gente que nunca te escribió).
- **El asistente solo contesta** a quien escribe. Los seguimientos son los dos que tú decidiste (a las 5 horas
  y a los 5 días), nunca campañas masivas.

Lo que **te toca a ti**:

- Usa un número **con historia** (de uso real desde hace tiempo), no una línea recién comprada.
- **Pide a la gente que guarde el número** en sus contactos. Los números que muchos guardan y con los que
  se conversa van menos al bloqueo.
- **No envíes mensajes masivos** ni listas de difusión desde ese número, ni por el teléfono.
- Activa la **verificación en dos pasos** de WhatsApp en ese número.
- Mantén el teléfono con batería e internet y **ábrelo al menos una vez cada pocos días**.
- No vincules y desvincules muchas veces seguidas.
- Si alguien reporta o bloquea al número, o WhatsApp muestra un aviso de «actividad inusual», **para** (ver
  sección 7) antes de que se agrave.
- Ten el **plan B** (sección 8) preparado de antemano, no el día del bloqueo.

## 7. Si WhatsApp lo desconecta

| Qué ves | Qué hacer |
|---|---|
| «Desconectado hace 2 o 3 min» | Nada: se reconecta solo (y si no, lo reinicia solo a los ~2 minutos y medio). |
| Aviso de Telegram: «lleva 10 min sin conexión» | Mira el estado. Pide a quien opera que lo **reinicie** (apéndice A, no pide QR). Revisa que el teléfono del negocio tenga internet. |
| **«Necesita QR»** o en el teléfono ya no aparece el dispositivo «DCASA Panama» | La vinculación se perdió (la quitaron desde el teléfono, o WhatsApp la cerró). Escanea un código nuevo (sección 3). Hasta entonces el asistente no contesta por WhatsApp. |
| Se desvincula **seguido** | No sigas reintentando: puede ser una señal de WhatsApp. Para y mira la sección 8. |
| WhatsApp **avisa o restringe** el número | **Para de inmediato:** borra el secreto `WA_TOKEN` en el panel de Cloudflare (el puente apaga el contenedor en un minuto; nada se borra y se puede reanudar). Sigue atendiendo desde el teléfono con normalidad y pasa al plan B. |
| Se perdió o se dañó la sesión guardada | Se restaura desde la copia diaria (apéndice B). Si no se puede, escanear un QR nuevo. |

El aviso de Telegram nunca lleva el código QR ni contraseñas; solo te dice qué pasa y dónde mirar.

## 8. «Coexistencia» y el plan B (la API oficial de Meta)

**La alternativa oficial** se llama *WhatsApp Cloud API*: Meta te da un acceso aprobado y el número está a
salvo. Cuesta poco: responder a un cliente dentro de las 24 horas de su último mensaje es gratis; escribir
primero o después de las 24 horas exige **plantillas aprobadas** que Meta cobra por mensaje (unos centavos).
Hay trámites con Meta (verificar el negocio con el RUC), y Meta ve que la atención es automatizada (lo
correcto: el asistente ya se presenta como automático y ofrece una persona).

**«Coexistencia»** es la forma de usar la API oficial **sin dejar de usar el teléfono**: el mismo número
queda a la vez en la app **WhatsApp Business** del teléfono y en la API. Tú y tus vendedoras siguen
contestando desde el teléfono y el asistente atiende por la API. Condiciones, según lo que leímos (no pudimos
abrir las páginas oficiales de Meta desde aquí: **confírmalas el día que decidas**):

- El número tiene que estar en la app **WhatsApp Business** (no en el WhatsApp normal).
- Hay que abrir la app en el teléfono **al menos cada 14 días** o se pausa el enlace.
- No sincroniza grupos ni mensajes temporales.

**Cuándo conviene pasar a la API oficial:**

- WhatsApp avisó, restringió o bloqueó el número, o se desvincula seguido sin explicación.
- El número de ventas se volvió demasiado importante para arriesgarlo (perderlo es perder el teléfono de la tienda).
- Quieres escribirle primero a muchos clientes (campañas, recordatorios): por QR eso es lo que más riesgo da.
- WhatsApp cambia su protocolo y el puente se rompe más de lo razonable.

El asistente **ya tiene el adaptador de la API oficial preparado y apagado** como plan B (docs/JUAN.md), así
que el cambio es encenderlo y apagar el puente.

> Recomendación honesta de la auditoría (docs/auditoria/ronda7/crm-whatsapp.md): para **el número de
> ventas**, lo más seguro es la API oficial con coexistencia; el QR queda mejor sobre **un segundo número**
> o como respaldo. La decisión de usarlo igual es tuya y ya la tomaste sabiéndolo.

## 9. Qué guarda el puente y qué no

- **Guarda**, cifrada, la sesión de WhatsApp (lo que evita escanear el QR cada vez) y sus copias de 7 días.
- **No guarda** los mensajes ni los archivos de los clientes: pasan directo al asistente. La única excepción
  son los mensajes que el asistente no pudo recibir, que esperan cifrados hasta 48 horas.
- **En los registros del sistema nunca** aparece el QR, una contraseña, un texto de cliente ni un número de
  teléfono completo (solo los últimos 4 dígitos).
- Los archivos que **recibimos** de clientes tienen tope de tamaño (fotos y audios hasta 10 MB, documentos y
  videos hasta 12 MB); si uno pasa, el asistente igual recibe el mensaje y sabe que había un archivo.
- Una foto de comprobante de pago o de identidad **no la ve la IA**: se anota para una vendedora (regla del
  asistente, docs/JUAN.md).

## 10. Cuánto cuesta

El contenedor del puente encendido todo el mes se midió en el CRM de origen en **≈ $1.50 a $2.00 al mes**,
dentro del plan de Cloudflare que ya pagas. (La alarma que lo vigila cada 30 segundos no se ha medido aún;
se mirará a las 24 horas del primer despliegue.) La copia en R2 está apagada: si la enciendes, es otro recurso
(centavos).

## 11. Decisiones que te tocan

1. **El número** que se vincula (tú lo decides al final). Recomendación: no el de ventas +507 6026-1919 si
   puedes evitarlo (sección 8).
2. ¿Quieres el **aviso por Telegram**? Necesita `TELEGRAM_BOT_TOKEN_JUAN` y `ALERTA_TELEGRAM_CHAT`.
3. ¿Quieres una **segunda copia de la sesión en R2**, fuera del sistema (protege si se borra el Worker por
   error)? Está apagada. Encenderla es un cambio pequeño de configuración y un bucket nuevo.
4. ¿Cuándo pasar al **plan B**? (sección 8).

---

# Apéndice para quien opera (técnico)

Todo con `WA_TOKEN` (**del gestor de contraseñas, no del chat**) en la variable `WA_TOKEN` de tu terminal:
`export WA_TOKEN='…'` y `PUENTE=https://dcasa-puente-wa.dcasapty.workers.dev` (o el de staging). El token va
siempre en la cabecera `Authorization: Bearer`; **nunca en la URL** (no se acepta).

## A. Rutas (todas con token salvo `/health`)

| Ruta | Para qué |
|---|---|
| `GET /health` | «ok». Sin token. |
| `GET /api/estado` | `estado` (`conectado` · `necesita_qr` · `desconectado` · `iniciando` · `apagado` · `sin_configurar`), `conectado`, `desconectado_min`/`desconectado_desde`, la sesión (`vinculado`, `instalacionCompleta`, `siguiente`, `sinSubir`, `preKeys`…), contadores, cuota, copias, `pendientes`, `secretos_faltantes`. Sin `WA_TOKEN` configurado responde igual, sin token, pero solo con los **nombres** que faltan. |
| `GET /api/qr` | El QR como imagen (`data:image/png;base64,…`) mientras sirve (<45 s); `null` si ya está conectado. Sin caché. Nunca se imprime en registros. |
| `POST /api/foto-perfil` | `{para}` (celular, jid de persona o `@lid`) → 200 `{ok, mime, base64}` con la foto pequeña de WhatsApp (`profilePictureUrl(jid,'preview')`, bajada solo de `pps.whatsapp.net` / `mmg.whatsapp.net`, hasta 300 KB); 404 si no tiene foto o no la deja ver (lo normal); 400 destino inválido (grupos y estados nunca); 409 sin conexión; 502 la descarga falló. No escribe nada ni cuenta para los topes de envío. |
| `POST /api/enviar` | `{para, chunks:[…], medios?:[{tipo:"imagen\|documento", url, nombre?, mime?, pie?}]}`. Respuestas: 200 `{ok, id_mensaje, ids, enviados}`; 400 cuerpo inválido; 409 sin conexión; 422 medio rechazado; 429 tope (`Retry-After`); 502 falla (con `parcial` e `ids` de lo que sí salió); 503 apagado o cola llena. |
| `POST /api/reiniciar` | Destruye y levanta el contenedor (**no pide QR**). Tras desplegar una imagen nueva, úsalo para que la tome. |
| `POST /api/desvincular` | Cierra la sesión en WhatsApp y la borra: pedirá QR. |
| `GET/POST /api/copias` · `GET /api/copias/exportar?id=` | Listar · sacar una copia ahora · bajar una copia (cifrada) como archivo. |
| `POST /api/restaurar` | Ver B. |
| `POST /api/podar` · `POST /api/recifrar` | Podar pre-keys (válvula manual) · recifrar con la clave nueva (C). |
| `/puente/*` | Solo del contenedor, con **su** token (derivado del `WA_TOKEN` por HMAC). Con `WA_TOKEN` no se abren, y con el del contenedor no se abre `/api/*`. |

Variables (en `puente-wa/wrangler.jsonc`): `PUENTE_ACTIVO`, `PUENTE_BASE_URL`, `MEDIOS_HOSTS_PERMITIDOS`
(dominios de los que se descargan medios: por defecto `dcasapty.com` y `dcasapty.workers.dev`),
`LIMITE_POR_MINUTO`, `LIMITE_POR_DIA`, `LIMITE_POR_DESTINATARIO_HORA`, `LIMITE_FRIOS_DIA`, `ALERTA_MINUTOS`,
`ALERTA_REAVISO_MINUTOS`, `COPIA_R2`. El mínimo entre burbujas (1 s) no baja de eso aunque se configure menos.

Cómo Juan debe usarlo (contrato, docs/JUAN.md): el celular va en E.164 sin «+» (`50760261919`); también se
aceptan `6026-1919`, `+507 6026 1919`, `00507…` y un jid. **Grupos, estados y canales se rechazan siempre.**
Se manda primero el texto y después los medios (cada imagen con su pie). Las imágenes y documentos los
**descarga el puente** (solo `https`, solo de los dominios permitidos, direcciones públicas, redirecciones
vigiladas, tipo y tamaño comprobados con el contenido real) y se envían ya descargados.

## B. Copias y restauración de la sesión

La sesión (`creds` y llaves de Signal) vive en el SQLite del Durable Object, **cifrada con `WA_SESION_CLAVE`**
(AES-GCM). Copias:

1. **Dentro del Durable Object**, siempre: una al vincular y luego **diaria**, 7 conservadas.
2. **R2, opcional y apagada** (`COPIA_R2` = «on» + bucket `COPIAS` enlazado en `wrangler.jsonc`). El código
   **no borra** objetos de R2: la retención se pone con una regla de ciclo de vida del bucket.
3. **A mano:** `curl -H "Authorization: Bearer $WA_TOKEN" "$PUENTE/api/copias/exportar" > sesion.json`
   (cifrada). **Guarda la copia y `WA_SESION_CLAVE` en lugares distintos**: la una sin la otra no sirve.

Restaurar (cuando la sesión se dañó pero WhatsApp no la desvinculó):

```
curl -s -H "Authorization: Bearer $WA_TOKEN" "$PUENTE/api/copias"                       # ver las copias
curl -s -X POST -H "Authorization: Bearer $WA_TOKEN" "$PUENTE/api/restaurar" \
     -d '{"copia":"2026-10-09T03-17-00Z"}'                                               # sin «copia»: la más reciente
# o desde un archivo exportado:  -d '{"archivo": <contenido de sesion.json>}'
# o desde R2:                    -d '{"origen":"r2","copia":"2026-10-09T03-17-00Z"}'
```

El puente apaga el contenedor, guarda lo que había como una copia más, comprueba que la copia se descifra con
la clave actual (si no, **no toca nada** y responde 422), la restaura de forma atómica y levanta el
contenedor con una **época nueva**. Si WhatsApp ya desvinculó el dispositivo desde el teléfono, ninguna copia
sirve: hay que escanear un QR nuevo. Si se pierde `WA_SESION_CLAVE`, las copias son inservibles.

## C. Rotar secretos

- **`WA_TOKEN`:** cámbialo en **los dos** Workers (puente y `juan`). El puente nota el cambio y reinicia solo
  el contenedor para que tome el token derivado nuevo (la sesión no se pierde). Habrá unos segundos de 401
  entre un cambio y el otro.
- **`WA_SESION_CLAVE`** (casi nunca): (1) pon la clave vieja en `WA_SESION_CLAVE_ANTERIOR` y la nueva en
  `WA_SESION_CLAVE`; (2) `POST /api/recifrar`; (3) `POST /api/copias` (las copias anteriores siguen cifradas
  con la clave vieja); (4) cuando ya no necesites las copias viejas, borra `WA_SESION_CLAVE_ANTERIOR`.

## D. Un solo escritor

Dos programas escribiendo la misma sesión de Signal la corrompen. Hay cuatro candados: `max_instances = 1`;
un único Durable Object (`idFromName("unico")`); una **cola** en el contenedor que manda de una petición a la
vez (así tampoco se entrelazan las burbujas de dos clientes); y una **época** que sube con cada arranque del
contenedor y que viaja en cada escritura: un contenedor «zombi» de una época anterior recibe 409 y no escribe.

## E. Despliegue (workflow manual)

`.github/workflows/desplegar-puente.yml` (Actions → *Desplegar puente de WhatsApp*), **solo a mano**:
`entorno` (staging / production) y `accion` (**dry-run** por defecto / desplegar). El ensayo corre tipos,
pruebas, la configuración de Wrangler de los dos entornos y construye la imagen, sin tocar Cloudflare. Para
desplegar usa **solo** `CLOUDFLARE_API_TOKEN` y `CLOUDFLARE_ACCOUNT_ID` (con permiso *Cloudflare Images: Edit*
para subir la imagen); no lee ni sube secretos del puente, y el primer despliegue sale bien sin ellos.
Comprueba antes que exista el Worker `dcasa-juan` (producción) o `dcasa-juan-staging` (staging), porque el
puente lo enlaza por service binding y Cloudflare no despliega un enlace a un Worker que no existe.
**Orden:** `juan` primero, puente después, secretos en el panel al final. Wrangler va **fijado** por el
`package-lock.json` (una versión nueva rompió el despliegue del CRM de origen sin que nadie tocara nada).
**Staging** (`dcasa-puente-wa-staging`) tiene su propia sesión y su propio contenedor: vincúlale siempre un
número de **pruebas**, nunca el del negocio, y nunca el mismo número en los dos entornos (se expulsarían).

## F. Tropiezos que ya pagó el CRM de Baby Caleb, y dónde quedaron cubiertos

| Tropiezo | Cómo queda cubierto aquí |
|---|---|
| El contenedor vive mientras vive su Durable Object (una noche muda) | El DO extiende `Container`, vigila por `schedule()` cada 30 s sin retroceso y renueva la actividad; **un cron cada minuto** revive la cadena si se cortó. Un solo dueño programa. |
| Un fallo al reconectar cortaba la cadena para siempre | `programarReconexion` encadena siempre el siguiente intento; el vigilante interno rescata sockets «zombi». |
| Dos sockets sobre el mismo número se expulsan | `cerrarAnterior()` + generaciones, `max_instances = 1`, época. |
| Vinculaba y se caía a los segundos (812 llaves en <30 s) | Almacén **por lotes**: una petición lleva todo el lote; probado con 812 llaves. `instalacionCompleta` (`sinSubir == siguiente`) es la señal que de verdad dice «terminó de instalarse». |
| 401 «mudo» por un token con caracteres fuera de ASCII | `WA_TOKEN` se exige ASCII (se reporta en `/api/estado`); el token del contenedor es hexadecimal. |
| Error 1042 al llamar Worker a Worker por URL pública | Todo por **service binding** (`JUAN`). |
| El bot contestaba encima de la dueña | Cada envío anota su id **antes** de enviar; un mensaje propio no anotado = persona → `propio:true`. Los ids se recuerdan 2 h en el DO (sobreviven a reinicios). |
| Conversaciones fantasma por estados/grupos | `esChatDeUnaPersona` al entrar y al salir. |
| Notas de voz y fotos llegaban vacías | Se descargan en el momento y viajan en base64; si no se puede, se dice (`medio_omitido`). |
| `unhandledRejection` mataba Node 22 | Capturado en `servidor.mjs`. |
| QR vencido → «revisa tu conexión» | El QR se sirve solo si tiene menos de 45 s y nunca con la sesión conectada. |
| `npx wrangler@4` rompió el despliegue | Wrangler fijado en el lock; el workflow usa `npm ci`. |
| Una prueba que pasa no dice que el sistema funcione | Prueba de punta a punta (`test/integracion.test.ts`) y el estado muestra `instalacionCompleta`. |

Pendiente de medir en producción real: el costo de 24 horas del Durable Object con su alarma, y todo lo que
solo se ve con WhatsApp de verdad (la primera vinculación y el primer día de uso).
