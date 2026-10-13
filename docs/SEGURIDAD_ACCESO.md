# Seguridad de acceso al panel de D'CASA

Cómo se entra al panel (Odoo) de forma segura, cómo se activa el doble factor, qué hacer si se
pierde el teléfono y qué se hará en Cloudflare cuando `dcasapty.com` esté en Cloudflare.
Módulo: `addons/dcasa_seguridad`. Borde: `edge/src/bots.ts`.

> En corto: **clave + código del teléfono** para los administradores, intentos fallidos que
> se castigan cada vez más, aviso a tu Telegram cuando alguien entra como administrador,
> sesiones que vencen solas, y un borde que corta a los robots antes de que lleguen a Odoo.

---

## 1. Qué hay hoy (sin que nadie haga nada)

| Protección | Dónde | Estado |
|---|---|---|
| Doble factor con app de códigos (Google Authenticator, Microsoft Authenticator…) | Odoo `auth_totp` | **Obligatorio para administradores** en staging y producción (§3) |
| Llaves de acceso (passkeys: huella o cara del teléfono/computadora) | Odoo `auth_passkey` | Disponible |
| Bloqueo progresivo por intentos fallidos | `dcasa_seguridad` | Activo: 5 fallos desde una IP → espera 1 min, luego 2, 4, 8… hasta 30 min |
| Límite del doble factor | Odoo | Activo: 5 códigos por hora por usuario |
| Registro de inicios de sesión | Ajustes › Usuarios y compañías › **Accesos al panel** | Activo: correctos, clave mala, código malo, IP y navegador. 180 días |
| Aviso de cada inicio de sesión del personal | Telegram de Brian | Activo si algún administrador tiene Telegram vinculado con Brian (§8.1) |
| Sesión de administrador | Odoo `auth_timeout` | Se cierra sola a las **12 h**; pantalla bloqueada (pide la clave) tras **60 min** sin uso |
| Gestor de bases de datos (`/web/database/*`) | `list_db = False` + borde | Cerrado desde internet (404 en el borde) |
| API de Odoo por XML-RPC/JSON-RPC (`/jsonrpc`, `/xmlrpc`, `/json/2`) | Borde | Cerrada desde internet |
| Cabeceras HTTPS (HSTS, nosniff, anti-iframe ajeno) | Borde | Activas en todas las respuestas |
| Rutas de sondeo (`/wp-admin`, `/.env`, `*.php`…) y escáneres (`sqlmap`, `nikto`…) | Borde | 404 / 403 sin despertar a Odoo |
| Límite de intentos por IP en login, clave, registro, formularios, /socios y carrito | Borde | Activo (contador en memoria; mejor con el binding de Cloudflare, §7) |
| Cloudflare Turnstile (captcha invisible) | Odoo `website_cf_turnstile` | **Listo y apagado** hasta tener las claves (§6) |
| **La puerta del equipo** (PIN al correo con Cloudflare Access antes de la clave) | Borde + `dcasa_seguridad` | **Staging en modo «1»**; producción en «0» hasta aclarar por qué `/master` daba «Not Found» (§8) |
| robots.txt para rastreadores de IA | `dcasa_seguridad` | Política «equilibrada» (§6.3) |

**Lo que NO se rompe:** Brian por MCP entra con **clave de API** (no con contraseña ni con
código), así que el doble factor no le afecta; Telegram entra por su webhook con secreto; el
despliegue y los respaldos no usan usuarios de Odoo. Con la app enrolada, Odoo ya **no acepta tu
contraseña por RPC**, solo claves de API: es justo lo que se quiere (está probado en los tests).

---

## 2. La dueña activa su doble factor (paso a paso, 5 minutos)

Hazlo **en la computadora**, con el teléfono a mano.

1. En el teléfono instala **Google Authenticator** o **Microsoft Authenticator** (gratis, App
   Store / Play Store). Si ya usas un gestor de claves con códigos (1Password, Bitwarden), sirve.
2. En el panel: arriba a la derecha, tu foto → **Mis preferencias** → pestaña **Seguridad**.
3. En «Autenticación de dos factores», activa el interruptor. Odoo te pide tu clave otra vez.
4. Aparece un **código QR**. En la app del teléfono toca **+** → **Escanear código QR**.
5. La app muestra «D'CASA…» con 6 números que cambian cada 30 s. Escríbelos en Odoo y confirma.
6. **Copia de seguridad (importante):** en el mismo momento escanea ese QR también en un segundo
   aparato (una tablet, o el gestor de claves). Odoo no da «códigos de respaldo»: el segundo
   aparato es tu respaldo. Si no pudiste, mira §4.
7. Prueba: cierra sesión y vuelve a entrar. Tras la clave te pedirá el código. Puedes marcar
   «No volver a preguntar en este dispositivo» en tu computadora de confianza (90 días).

**Opcional, más cómodo y aún más seguro:** en la misma pestaña, **Llaves de acceso** →
**Agregar llave de acceso**. Luego en la pantalla de entrada usas «Entrar con llave de acceso»
(huella o cara). Una llave de acceso ya es doble factor por sí sola.

---

## 3. Encender la obligatoriedad (cuando la dueña ya tiene su app)

> **Estado actual (2026-10-13):** **staging y producción están ENCENDIDOS** (`"DCASA_2FA_OBLIGATORIO": "1"`,
> alcance `admins`; la dueña ya probó el flujo en staging). En cuanto se despliegue, el primer
> administrador que entre verá el QR después de su clave: ten el teléfono a mano y sigue el §2.
> Para apagarlo por una emergencia: poner `"0"` y desplegar (o §4 si solo falta el teléfono).

Mientras esté apagada, cada quien decide. Encendida, **todo administrador que aún no tenga la
app la enrola al entrar**: después de la clave ve el QR, escanea, escribe el código y recién
entonces se abre el panel. Sin código no hay panel.

1. Verifica que tú ya entras con el código (§2, paso 7).
2. En `edge/wrangler.jsonc` → `vars`, cambia `"DCASA_2FA_OBLIGATORIO": "0"` por `"1"` (y en
   `env.staging` si quieres probar ahí primero).
3. Despliega (como siempre: Actions › Desplegar). El arranque escribe en el log a quién le
   tocará enrolar: `▶ 2FA obligatorio: estos administradores enrolarán la app al entrar: …`.
4. Para incluir a **todo el personal** (vendedoras incluidas), además `"DCASA_2FA_ALCANCE":
   "internos"`. Los clientes del portal y los socios (/socios con PIN) nunca entran en esto.

Notas:
- La variable manda: en cada arranque el contenedor la vuelve a escribir en Odoo
  (`dcasa_seguridad.2fa_obligatorio`). Cambiarla a mano en Parámetros del sistema dura hasta el
  próximo reinicio.
- **Por qué no se usa la opción de Odoo «Exigir 2FA» (código por correo):** con esa opción, quien
  no tiene app recibe el código **por correo**. D'CASA todavía no tiene servidor de correo saliente
  (docs/PLAN.md), así que nadie recibiría el código y **todos quedarían fuera**. No la actives en
  Ajustes › Permisos; si alguien la activa sin correo, el arranque lo avisa en el log. Cuando haya
  correo saliente se puede reconsiderar, pero la opción de D'CASA (enrolar la app al entrar) es
  más segura que un código por correo.
- Riesgo que hay que conocer: si alguien ya sabe la clave de un administrador que **todavía no**
  enroló, podría enrolar su propio teléfono. Por eso: primero todos los administradores enrolan,
  luego se enciende; y cada enrolamiento queda en «Accesos al panel» y avisa por Telegram.

---

## 4. Rescate: perdí el teléfono («break-glass»)

Ninguna de estas salidas es una puerta trasera: todas exigen otra credencial fuerte que ya
existe (otro administrador con su propio 2FA, o permiso para desplegar en GitHub/Cloudflare,
que tienen su propio 2FA) y todas quedan registradas.

**A. Tienes el respaldo** (tablet o gestor de claves del §2 paso 6): entra con él y listo. Luego,
en Mis preferencias › Seguridad, desactiva y vuelve a activar el 2FA con el teléfono nuevo.

**B. Hay otro administrador:** él entra, va a **Ajustes › Usuarios y compañías › Usuarios** →
tu usuario → pestaña **Seguridad** → **Deshabilitar** la autenticación de dos factores (Odoo le
pide su propia clave). Tú entras solo con clave y activas el 2FA con el teléfono nuevo (§2).
Recomendación: que siempre haya **dos** administradores con 2FA (la dueña y una persona de
confianza), justamente para esto.

**C. Eres la única administradora y no tienes respaldo:** se hace desde el despliegue.
1. En GitHub › Settings › Secrets and variables › Actions, o en `edge/wrangler.jsonc` → `vars`,
   agrega `DCASA_2FA_RESCATE` con **tu usuario** (el login, p. ej. tu correo).
2. Despliega. Al arrancar, el contenedor le quita el doble factor a ese usuario **una sola vez
   por versión** y lo deja en «Accesos al panel» como «Rescate» (y en el log).
3. Entra con tu clave, activa el 2FA con el teléfono nuevo (§2).
4. **Quita `DCASA_2FA_RESCATE`** y vuelve a desplegar. Mientras siga puesta, el log lo recuerda en
   cada arranque.

**D. Además olvidaste la clave:** otro administrador te pone una clave nueva (Usuarios › tu
usuario › Cambiar contraseña). Si no hay otro administrador, abre una conversación con quien
mantiene el sistema: se hace con `odoo shell` en una restauración del respaldo (docs/OPERACION.md),
nunca con una clave escondida.

**Lo más importante de todo:** la cuenta de **Cloudflare** y la de **GitHub** son la llave
maestra (pueden desplegar y leer respaldos). Las dos con 2FA y con sus **códigos de recuperación
impresos** y guardados en un lugar físico seguro.

**Si Turnstile no deja entrar** (p. ej. clave mal copiada): `DCASA_TURNSTILE=off` en las
variables y desplegar. **Si la puerta del equipo (Cloudflare Access) no deja entrar:** `DCASA_PUERTA_OBLIGATORIA` en `"0"` y
desplegar (§8.6).

---

## 5. Endurecimiento que ya está (detalle técnico)

- **Bloqueo progresivo** (`res.users._on_login_cooldown`): base de Odoo `base.login_cooldown_after`
  = 5 fallos, `base.login_cooldown_duration` = 60 s; cada fallo nuevo duplica la espera hasta
  `dcasa_seguridad.bloqueo_tope_s` (1800 s). Es **por IP** (con `proxy_mode` y el Worker, la IP
  real), no por usuario: así nadie puede dejar a la dueña fuera escribiendo mal su clave a
  propósito. El contador vive en memoria: un reinicio lo pone en cero.
- **Registro** (`dcasa.seguridad.acceso`): solo lectura para administradores; nadie lo edita ni lo
  borra a mano. Los fallos se guardan aunque la petición se deshaga (cursor aparte) y, si hay
  un ataque con más de 500 fallos en una hora, se dejan de guardar (siguen en el log) para no
  llenar la base. Además Odoo trae **Ajustes › Usuarios › Dispositivos** (sesiones abiertas, con
  botón para cerrarlas).
- **Avisos por Telegram** (si `dcasa_brian` está instalado y el usuario vinculó su Telegram):
  cada vez que entra alguien del personal (con IP, navegador y hora de Panamá; antes solo los
  administradores), cuando llega a 5 claves malas seguidas y cuando alguien enrola el 2FA. Van a
  ese usuario y a los demás administradores vinculados. `DCASA_AVISO_LOGIN_TELEGRAM`: `1` (todo el
  personal), `admins` (solo administradores) o `0` (apagados).
- **Sesiones de administrador** (`auth_timeout`, grupo Administración/Ajustes): cierre a las 12 h
  (`DCASA_SESION_ADMIN_HORAS`), bloqueo de pantalla tras 60 min sin uso
  (`DCASA_INACTIVIDAD_ADMIN_MIN`). Se ajusta también en Ajustes › Usuarios › Grupos ›
  Administración / Ajustes. Vendedoras, portal y socios no cambian. Las 12 h se cuentan desde que
  entraste (`models/ir_http.py`): el `auth_timeout` de Odoo solo las contaría desde la última
  rotación de la sesión (cada 3 h), y quien usa el panel sin parar nunca saldría.
- **Borde** (`edge/src/routing.ts`): HSTS, `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options: SAMEORIGIN` y `Content-Security-Policy: frame-ancestors 'self'` (sin pisar la
  CSP que mande Odoo). `/web/database/*`, `/jsonrpc`, `/xmlrpc`, `/json/2` y `/doc-bearer`
  bloqueados con 404 (tests en `edge/test/routing.test.ts` y `edge/test/bots.test.ts`).

---

## 6. Robots y agentes automatizados

### 6.1 En el borde (ya activo, gratis)

`edge/src/bots.ts`, antes de despertar a Odoo:

1. **Rutas de sondeo** → 404: `/wp-admin`, `/wp-login.php`, `/xmlrpc.php`, `/.env`, `/.git`,
   `/phpmyadmin`, `/vendor/phpunit`, `/cgi-bin`, `/actuator`, cualquier `*.php`, `*.asp`, `*.sql`…
   (`/.well-known` sí pasa).
2. **Escáneres que se anuncian** (sqlmap, nikto, nmap, nuclei, wpscan, acunetix, gobuster…) → 403.
   **Nunca** se tocan Googlebot, Bingbot, los previsualizadores de WhatsApp/Facebook/Telegram, los
   agentes de IA que buscan para una persona ni las librerías genéricas (Brian, Telegram e
   integraciones las usan).
3. **Límite por IP** (por minuto): 10 en login/2FA/clave/registro/`/socios`, 10 en formularios del
   sitio, 120 en carrito y pago → 429 «Demasiados intentos seguidos» con `Retry-After: 60`.
   Son generosos a propósito: en Panamá mucha gente comparte la IP del operador móvil.
   `/brian/*` no entra (MCP tiene su propio límite por usuario).

El límite usa un contador en memoria (aproximado: cada ubicación de Cloudflare cuenta por su
lado). Para un contador de Cloudflare, descomenta `ratelimits` en `edge/wrangler.jsonc`
(**Rate Limiting de Workers**: no se crea ningún recurso aparte, `namespace_id` es un número que
elegimos, y no tiene costo propio; periodos de 10 o 60 s). Hay que repetirlo dentro de
`env.staging` si se quiere en staging.

### 6.2 Turnstile (captcha invisible de Cloudflare) — listo, apagado

Odoo 19 trae `website_cf_turnstile`: con las claves puestas, el widget aparece solo en el
**login**, el **registro**, el **cambio de clave**, los **formularios del sitio** (contacto) y en
**/socios** (entrar y registrarse), y Odoo valida el token con Cloudflare en el servidor. Casi
nadie ve nada: solo si Cloudflare duda, aparece una casilla. Sin claves no hace nada.

Crear el widget (lo hace la dueña, o quien mantiene el sistema con su aprobación; es gratis,
hasta 20 widgets por cuenta):
1. Cloudflare › **Turnstile** › **Add widget**. Nombre: «D'CASA sitio». Hostnames:
   `dcasapty.com` y `staging.dcasapty.com` (y el `*.workers.dev` mientras no haya dominio).
   Modo: **Managed**.
2. Copia la **Site key** y la **Secret key**.
3. Site key → `edge/wrangler.jsonc` → `vars` → `"TURNSTILE_SITE_KEY": "…"`. Secret key → secreto
   de GitHub `TURNSTILE_SECRET` (el despliegue lo sube al Worker).
4. Despliega y prueba en staging: entrar, el formulario de contacto y /socios.
5. Si algo falla: `DCASA_TURNSTILE=off` y desplegar (§4).

### 6.3 robots.txt para rastreadores de IA

`/robots.txt` lo arma Odoo y `dcasa_seguridad` agrega al final la política de IA
(`DCASA_ROBOTS_IA` → `dcasa_seguridad.robots_ia`):

| Política | Entrenamiento de IA (GPTBot, ClaudeBot, Google-Extended, CCBot, Bytespider, Meta-ExternalAgent…) | Búsqueda y respuestas de IA (ChatGPT-User, OAI-SearchBot, Claude-User, PerplexityBot…) |
|---|---|---|
| `abierta` | permitido | permitido |
| **`equilibrada`** (por defecto, propuesta) | **bloqueado** | **permitido** |
| `cerrada` | bloqueado | bloqueado |

**Propuesta: `equilibrada`.** Los rastreadores de entrenamiento se llevan las fotos y textos del
catálogo sin mandar clientes; los de búsqueda y respuesta («¿dónde compro un sofá en La
Chorrera?») sí pueden citar la tienda y traer visitas. Google y Bing normales nunca se bloquean
(el sitio vive de SEO), ni los previsualizadores de enlaces (WhatsApp, Facebook).

Esto **no cambia** lo que dice la [política de privacidad](/privacidad#inteligencia-artificial)
sobre Brian: allí se explica que Brian usa a Meta como proveedor de IA y que Meta puede usar lo
que se le envía para entrenar sus modelos. Eso es lo que D'CASA **le manda** a Meta al usar
Brian; robots.txt es otra cosa: si los rastreadores pueden **leer solos** el sitio público.

robots.txt es un pedido de buena fe; quien no lo respete se frena en Cloudflare (§7).

---

## 7. Cloudflare cuando `dcasapty.com` esté en Cloudflare (solo documentado)

Nada de esto está activado: se hace en el panel de Cloudflare cuando el DNS del dominio esté
en Cloudflare. Costos verificados en la documentación de Cloudflare (octubre 2026); confirmar
el precio vigente antes de contratar algo de pago.

| Qué | Plan | Recomendación |
|---|---|---|
| **AI Crawl Control / Block AI bots** | Todos, incluido Free | Configurar las tres conductas: **Training = bloquear**, **Search = permitir**, **Agent = permitir** (misma idea que robots.txt, pero obligatorio para los que no lo respetan) |
| **Bot Fight Mode** | Free | **Con cuidado.** No admite excepciones: puede desafiar al webhook de **Telegram**, a los clientes **MCP** de Brian y a monitores. Probar primero en staging; si Telegram deja de responder, apagarlo |
| **Super Bot Fight Mode** | Pro, Business, Enterprise (de pago) | Mejor que Bot Fight Mode porque **sí admite excepciones** (saltar `/brian/*`). Evaluar si el tráfico de bots molesta |
| **Reglas WAF personalizadas** | Free (pocas reglas) | 1) bloquear rutas de sondeo (ya lo hace el Worker, pero así ni se cobra la invocación); 2) desafío gestionado a `POST /web/login` desde fuera de Panamá **solo si** la dueña no viaja |
| **Rate limiting rules** | Free: 1 regla, periodo 10 s, bloqueo 10 s | `http.request.uri.path eq "/web/login" and http.request.method eq "POST"`: 5 por 10 s por IP → bloquear |
| **Rate Limiting de Workers** (binding) | Workers (sin costo propio) | Descomentar `ratelimits` en `edge/wrangler.jsonc` (§6.1) |
| **Turnstile** | Gratis | §6.2 |
| **Managed robots.txt** | Todos | **No** activarlo: ya tenemos robots.txt propio; Cloudflare antepondría el suyo |

---

## 8. La puerta del equipo (Cloudflare Access + clave + código de la app)

> **Estado (2026-10-13):** **staging está en modo `"1"`** (el personal solo entra por `/master`; por `/web/login` ya no;
> la puerta en «1» todavía no se probó de punta a punta allí). **Producción volvió a `"0"`**: con «1», `/master` respondía
> «Not Found» después del PIN de Access (el borde rechazó el pase) y el personal se quedó sin entrada. Antes de volver a
> encenderla hay que ver el motivo en los logs del Worker de producción (`puerta_token_rechazado`, campo `motivo`: audiencia,
> emisor, llave desconocida, firma, vencido o sin correo) y probar la entrada **con el interruptor en `"0"` y de nuevo con
> `"avisar"`** (§8.5) antes de pasar a `"1"`. Cada entorno tiene su aplicación de Cloudflare Access («Master (staging)» y
> «Master (producción)», política «Equipo D'CASA») y sus cuatro secretos: son del entorno, no se heredan del otro. El modo
> `"1"` bloquea el login público únicamente si la puerta está completa (los cuatro secretos).
>
> *Historia:* el 2026-10-10 el código quedó construido y probado, apagado hasta cargar los secretos del §8.4 y encender los
> pasos del §8.5. Pedido de la dueña: que el personal **no** inicie sesión por la página web
> pública (esa entrada es solo para clientes y socios), que antes de ver siquiera la pantalla de la clave haya un
> filtro de Cloudflare que mande un PIN al correo, que el equipo entre por su propia página (`/master`) con correo y
> clave **o con llave de acceso**, que **siempre** pidan el código de Google Authenticator (también con la llave: una
> huella o una cara se pueden falsificar) y que cada acceso avise al canal del administrador.

### 8.1 Cómo se entra (los tres pasos)

1. **El PIN al correo (Cloudflare Access).** El equipo abre **`https://<sitio>/master`**. Cloudflare pide el correo y
   manda un PIN de 6 números (dura 10 minutos). Solo llega a los correos que la dueña puso en la lista de Cloudflare.
2. **La página «Acceso del equipo»** (la misma dirección `/master`, ya servida por Odoo): **correo y contraseña, o llave
   de acceso** (huella o cara del aparato).
3. **El código de la app (Google Authenticator), SIEMPRE.** También con la llave de acceso, porque una huella o una cara
   se pueden falsificar; y **sin** la casilla «No volver a preguntar en este dispositivo» (Odoo la ofrece por 90 días;
   para el personal está desactivada). Quien todavía no tiene la app la enrola en ese momento (§2).

Después de pasar el paso 1 el navegador queda con una cookie que dura **12 horas** (nunca más que la sesión de
Cloudflare) y se borra sola al **cerrar sesión** en Odoo. Pasado ese tiempo hay que pasar el PIN otra vez. Con el
modo «1», si a alguien se le vence la sesión y Odoo lo manda al login público (`/web/login?redirect=/odoo…`), el borde
lo lleva solo a `/master`.

**Cada acceso avisa.** Cada inicio de sesión del personal manda un aviso al **Telegram de los administradores
vinculados con Brian** (el del dueño): quién, desde qué IP y navegador, a qué hora y con qué correo pasó la puerta.
`DCASA_AVISO_LOGIN_TELEGRAM`: `1` (todo el personal, por defecto), `admins` (solo administradores, como antes) o `0`
(nada). Además quedan en **Accesos al panel** (180 días).

### 8.2 Qué cambia para cada quien

| Quién | Qué pasa |
|---|---|
| **Personal** (Odoo «usuario interno») | Solo inicia sesión **en `/master`** y solo sigue dentro si pasó por la puerta. Si escribe su clave en `/web/login` (el login público), aunque sea correcta, ve el mismo «usuario o contraseña incorrectos» de siempre (no se le dice por qué); queda anotado en **Accesos al panel** («Clave correcta, pero sin pasar por la puerta» o «Intentó entrar por el login público») y, si era un administrador, llega un aviso a Telegram. |
| **Clientes del portal y socios** | Nada. Siguen entrando por `/web/login` (clientes) y `/socios` (celular + PIN). |
| **Quien teclea `/odoo` sin permiso** | `404 Not Found`, como una página que no existe. (`/web` lleva al login público, donde el personal ya no puede entrar.) |
| **Brian (MCP y Telegram), Juan, el despliegue y los respaldos** | Nada: no usan sesión de personal (clave de API, secreto del webhook, tokens). |

### 8.3 Dos listas, no una (y en qué orden)

La duda natural: «¿primero hago las políticas en Cloudflare o primero creo los usuarios en Odoo?». **Son dos listas
distintas y las dos hacen falta**:

| Lista | Dónde | Qué decide |
|---|---|---|
| **Correos permitidos** | Cloudflare › Zero Trust › Access (política «Equipo D'CASA») | Quién puede **ver la entrada** y recibir el PIN. |
| **Usuarios** | Odoo › Ajustes › Usuarios | Quién puede **iniciar sesión** y qué puede hacer dentro. |

- **Orden para empezar:** los usuarios de Odoo ya existen; entonces crea la política de Access con **los mismos
  correos**. Para una persona nueva: **1)** su usuario en Odoo (con su correo en el campo *Correo electrónico*),
  **2)** su correo en la política de Access.
- **El amarre** (`DCASA_PUERTA_EXIGIR_CORREO=1`, recomendado cuando todo funcione): el correo con el que se pasó la
  puerta tiene que ser el correo (o el usuario) de la cuenta de Odoo. Así nadie pasa la puerta con su correo y entra
  con la cuenta de otra persona, y queda escrito en **Accesos al panel** quién pasó por cada inicio de sesión.
- **Para dar de baja a alguien:** **1)** archivar su usuario en Odoo, **2)** quitar su correo de la política de Access.
  Su cookie de la puerta vence sola en ≤ 12 h; para cortarla ya, en Zero Trust › *Users* revoca su sesión.

### 8.4 Preparación (la hace la dueña, una vez por entorno; staging primero)

Los valores secretos los pegas tú en GitHub; nunca se escriben en el chat ni en el repositorio.

**A. Cloudflare Zero Trust** (gratis hasta 50 personas; Cloudflare puede pedir una tarjeta sin cobrar):
1. Cloudflare › **Zero Trust** → elige el nombre del equipo (p. ej. `dcasa` → `dcasa.cloudflareaccess.com`) → plan **Free**.
2. Zero Trust › **Integrations › Identity providers › Add new identity provider › One-time PIN**. **En cuentas nuevas
   el PIN por correo NO viene activado** (Cloudflare pone por defecto su propio login de cuenta): hay que agregarlo.
   Debe aparecer como «ADDED».
3. Zero Trust › **Access controls › Applications › Add an application › Self-hosted**:
   - **Application name:** «Master (staging)».
   - **Public hostname:** el del sitio (staging: `dcasa-staging.dcasapty.workers.dev`; producción: `dcasapty.com`) y
     **Path:** `master*`.
   - **Policy:** nombre «Equipo D'CASA», acción **Allow**, regla **Include › Emails** y los correos del equipo.
   - **Login methods:** desmarca «aceptar todos» y deja **solo One-time PIN**.
   - **Session duration:** 24 horas. Guarda.
   - Abre la aplicación y copia el **Application Audience (AUD) Tag** (es un texto largo de letras y números).
   - Si Cloudflare no te deja poner una ruta sobre un `workers.dev`, avísame: hay una alternativa (proteger todo
     staging mientras se prueba, o esperar al dominio propio).

**B. Los cuatro secretos** (GitHub › Settings › Environments › *staging* (y luego *production*) › Secrets):

| Secreto | Qué poner |
|---|---|
| `DCASA_PUERTA_RUTA` | `/master` (con barra; es la **misma** ruta de la aplicación de Access). Puede ser otra palabra (3 a 64 letras minúsculas, números o guiones; no puede ser una ruta del sitio como `/odoo`, `/web` o `/shop`): una más rara es más discreta, pero lo que protege es el PIN, no el nombre. |
| `DCASA_PUERTA_SECRETO` | 32+ caracteres al azar: `openssl rand -hex 32`. Distinto por entorno. Firma la cookie y las cabeceras hacia Odoo. |
| `DCASA_ACCESS_EQUIPO` | `https://dcasa.cloudflareaccess.com` (con el nombre de **tu** equipo). |
| `DCASA_ACCESS_AUD` | El *AUD Tag* que copiaste. |

Las cuatro juntas o ninguna: si falta alguna o está mal copiada, **la puerta queda apagada** y se escribe el motivo en
los logs del Worker (`puerta_incompleta`); nunca queda a medias.

### 8.5 Encender, sin quedarte fuera (en este orden)

El interruptor es `DCASA_PUERTA_OBLIGATORIA` (en `edge/wrangler.jsonc` → `vars`, uno por entorno):

1. **Con los secretos cargados y el interruptor en `"0"`**: despliega. La puerta ya **abre**, pero no obliga. Prueba:
   abre `https://<sitio>/master` → te pide el correo → PIN → aparece «Acceso del equipo» → correo y clave (o llave de
   acceso) → código de la app → llegas al panel. En el log del Worker aparece `puerta_abierta`.
2. **`"avisar"`**: nadie se queda fuera, pero cada inicio de sesión del personal **sin** puerta queda anotado
   (Ajustes › Usuarios › **Accesos al panel** › filtro «Sin pasar por la puerta»). Úsalo unos días, hasta que no
   salga nadie del equipo.
3. **`"1"`**: el personal solo entra por la puerta y por `/master`, `/odoo` sin permiso da 404, y quien aún no tiene la
   app la enrola al entrar (el código es obligatorio para todo el personal). Si quieres el amarre, también
   `DCASA_PUERTA_EXIGIR_CORREO` en `"1"` (primero comprueba que el correo de cada usuario de Odoo es el mismo que
   está en Access).
4. **Producción:** repite A y B con su propia aplicación de Access (otro hostname, otro *AUD Tag*, otro secreto) y
   los mismos tres pasos de este apartado. Producción usa el dominio definitivo cuando esté en Cloudflare.

Nada de esto toca a clientes ni a socios.

### 8.6 Si la puerta no abre (rescate)

- **Cloudflare Access caído, PIN que no llega, correo sin acceso, secreto o *AUD Tag* mal copiado:** pon
  `DCASA_PUERTA_OBLIGATORIA` en **`"0"`** en `edge/wrangler.jsonc` y despliega (o vuelve atrás el despliegue:
  docs/OPERACION.md → «Volver atrás un despliegue»). El modo lo decide el Worker en **cada petición**, así que en cuanto
  termina el despliegue el borde no cierra `/odoo` y Odoo no exige la puerta: se entra como antes (clave + código). No
  hace falta reiniciar a Odoo ni borrar nada en Cloudflare.
- **Seguros que ya trae:** una petición sin la cabecera firmada del modo no exige nada (por eso un error de copiar el
  secreto no deja a nadie fuera, y lo que nace dentro del contenedor, como el PDF de una factura, sigue funcionando);
  si falta alguno de los cuatro secretos, la puerta queda apagada.
- **Un detalle que NO se detecta solo:** un *AUD Tag*, un nombre de equipo o una ruta que están bien escritos pero son de
  otra aplicación pasan la validación de formato y la entrada no abre. Por eso el §8.5 manda probar la entrada con el
  interruptor en `"0"` antes de pasar a `"avisar"` y a `"1"`.
- **Alguien perdió su correo o el teléfono:** el §4 (el doble factor) sigue igual. Para el correo: otro administrador
  cambia el correo en Odoo y en la política de Access.

### 8.7 Cómo está armado (para quien mantiene el sistema)

- **Borde** (`edge/src/puerta.ts`, `handler.ts`): la entrada (`DCASA_PUERTA_RUTA`, p. ej. `/master`) es la página de
  login del equipo: lee el token que Access pone en `Cf-Access-Jwt-Assertion` y lo **verifica**: firma RS256 con las llaves de `<equipo>/cdn-cgi/access/certs`
  (guardadas 1 h; una sola descarga a la vez, con tiempo máximo y pausa tras un fallo), emisor, audiencia,
  vencimiento y un correo ASCII bien formado. Si Access estuviera mal configurado, la entrada no abre (404). Con el
  token bueno pone su propia cookie `__Host-dcasa_puerta` (HMAC con `DCASA_PUERTA_SECRETO`, HttpOnly, Secure,
  SameSite=Lax) y le entrega a la persona la página que da Odoo (GET y POST del formulario; nunca se guarda en caché).
  Cerrar sesión en Odoo (también con prefijo de idioma) borra la cookie. En modo «1», `/web/login?redirect=/odoo…`
  redirige a la entrada.
- **Hacia Odoo**, en cada petición, dos cabeceras firmadas con el mismo secreto: `X-Dcasa-Puerta` (quién pasó la puerta,
  solo si la pasó) y `X-Dcasa-Puerta-Modo` (el modo y el amarre del correo, válida 5 minutos). El borde **siempre** borra
  ambas de lo que manda el visitante y quita la cookie de la puerta del `Cookie` que viaja a Odoo.
- **Odoo** (`addons/dcasa_seguridad`): `controllers/master.py` sirve `/master` reutilizando el `web_login` de Odoo
  (clave, llave de acceso, Turnstile, bloqueo progresivo, segundo factor) con otra plantilla; `models/puerta.py`,
  `res_users.py` e `ir_http.py` verifican las firmas. Al iniciar
  sesión (usuarios internos) y en cada petición con sesión de un usuario interno exige la cabecera de la puerta; si
  falta, rechaza el inicio o **cierra la sesión y quita al usuario de esa misma petición** (sin eso, la última petición
  se ejecutaba aún con sus permisos: lo encontró la revisión independiente y lo cubre una prueba). Con modo `0` o sin
  cabecera de modo no exige nada.
- **Por qué una cookie propia y no solo la de Access:** así la ruta secreta es lo único que Access protege (se puede
  usar en un `workers.dev` o en el dominio, sin tocar la tienda ni el chat), no depende de cómo Cloudflare reparta su
  cookie por ruta y no afecta a los WebSockets del panel (el Access de un Worker entero no los admite).
- **Pruebas:** `edge/test/puerta.test.ts` (llaves RSA reales, tokens manipulados, `none`/HS256, cookie alterada, llaves
  y descargas) y `addons/dcasa_seguridad/tests/test_puerta.py` (inicio de sesión, sesión robada, modo falsificado,
  amarre del correo). Cada regla se rompió a propósito para comprobar que alguna prueba falla.

### 8.8 Límites que conviene conocer

- Las **claves de API** de usuarios internos (Brian por MCP) no pasan por la puerta: tienen su propia protección.
- Una conexión **WebSocket** ya abierta no se corta cuando vence la cookie; la siguiente petición sí.
- Si quitas a alguien de la política de Access, su cookie de la puerta vale hasta **12 horas** (o menos); para cortarla ya,
  archiva su usuario en Odoo y revoca su sesión en Zero Trust › *Users*.
- Un **correo con letras fuera de ASCII** (acentos, ñ) no puede usar la puerta: se rechaza a propósito para no romper las
  cabeceras HTTP. Usa una dirección sin esos caracteres.

---

## 9. Referencia rápida de variables

| Variable | Valores | Por defecto |
|---|---|---|
| `DCASA_2FA_OBLIGATORIO` | `0` / `1` | `0` |
| `DCASA_2FA_ALCANCE` | `admins` / `internos` | `admins` |
| `DCASA_2FA_RESCATE` | login del usuario a rescatar (quitar después) | — |
| `DCASA_SESION_ADMIN_HORAS` | horas, `0` = sin cierre | 12 (al instalar) |
| `DCASA_INACTIVIDAD_ADMIN_MIN` | minutos, `0` = sin bloqueo | 60 (al instalar) |
| `DCASA_AVISO_LOGIN_TELEGRAM` | `1` (todo el personal) / `admins` (solo administradores) / `0` (nada) | `1` |
| `DCASA_ROBOTS_IA` | `abierta` / `equilibrada` / `cerrada` | `equilibrada` |
| `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET` (secreto) | claves del widget | — (apagado) |
| `DCASA_TURNSTILE` | `off` = apagar | — |
| `DCASA_PUERTA_OBLIGATORIA` | `0` / `avisar` / `1` (§8.5) | `0` |
| `DCASA_PUERTA_EXIGIR_CORREO` | `0` / `1` (el correo de la puerta = el de la cuenta de Odoo) | `0` |
| `DCASA_PUERTA_HORAS` | 1 a 24: cuánto dura la puerta abierta | 12 |
| `DCASA_PUERTA_RUTA`, `DCASA_PUERTA_SECRETO`, `DCASA_ACCESS_EQUIPO`, `DCASA_ACCESS_AUD` (secretos de GitHub, las cuatro juntas) | datos de la entrada y de Access (§8.4) | — (puerta apagada) |

Parámetros de Odoo relacionados: `base.login_cooldown_after` (5), `base.login_cooldown_duration`
(60), `dcasa_seguridad.bloqueo_tope_s` (1800).
