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
| Doble factor con app de códigos (Google Authenticator, Microsoft Authenticator…) | Odoo `auth_totp` | Disponible para quien lo active. **No obligatorio** todavía |
| Llaves de acceso (passkeys: huella o cara del teléfono/computadora) | Odoo `auth_passkey` | Disponible |
| Bloqueo progresivo por intentos fallidos | `dcasa_seguridad` | Activo: 5 fallos desde una IP → espera 1 min, luego 2, 4, 8… hasta 30 min |
| Límite del doble factor | Odoo | Activo: 5 códigos por hora por usuario |
| Registro de inicios de sesión | Ajustes › Usuarios y compañías › **Accesos al panel** | Activo: correctos, clave mala, código malo, IP y navegador. 180 días |
| Aviso de inicio de sesión de administrador | Telegram de Brian | Activo si tu usuario tiene Telegram vinculado con Brian |
| Sesión de administrador | Odoo `auth_timeout` | Se cierra sola a las **12 h**; pantalla bloqueada (pide la clave) tras **60 min** sin uso |
| Gestor de bases de datos (`/web/database/*`) | `list_db = False` + borde | Cerrado desde internet (404 en el borde) |
| API de Odoo por XML-RPC/JSON-RPC (`/jsonrpc`, `/xmlrpc`, `/json/2`) | Borde | Cerrada desde internet |
| Cabeceras HTTPS (HSTS, nosniff, anti-iframe ajeno) | Borde | Activas en todas las respuestas |
| Rutas de sondeo (`/wp-admin`, `/.env`, `*.php`…) y escáneres (`sqlmap`, `nikto`…) | Borde | 404 / 403 sin despertar a Odoo |
| Límite de intentos por IP en login, clave, registro, formularios, /socios y carrito | Borde | Activo (contador en memoria; mejor con el binding de Cloudflare, §7) |
| Cloudflare Turnstile (captcha invisible) | Odoo `website_cf_turnstile` | **Listo y apagado** hasta tener las claves (§6) |
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
variables y desplegar. **Si Cloudflare Access no deja entrar** (cuando exista, §8): en el panel
de Cloudflare › Zero Trust › Access › Applications, deshabilita la aplicación del panel.

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
  cada vez que entra un administrador (con IP, navegador y hora de Panamá), cuando llega a 5
  claves malas seguidas y cuando alguien enrola el 2FA. Van a ese usuario y a los demás
  administradores vinculados. `DCASA_AVISO_LOGIN_TELEGRAM=0` los apaga.
- **Sesiones de administrador** (`auth_timeout`, grupo Administración/Ajustes): cierre a las 12 h
  (`DCASA_SESION_ADMIN_HORAS`), bloqueo de pantalla tras 60 min sin uso
  (`DCASA_INACTIVIDAD_ADMIN_MIN`). Se ajusta también en Ajustes › Usuarios › Grupos ›
  Administración / Ajustes. Vendedoras, portal y socios no cambian.
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

## 8. Plan: Cloudflare Access (Zero Trust) delante del panel

Una puerta más **antes** de Odoo: para ver siquiera la pantalla de login del panel hay que
pasar por Cloudflare (código al correo o cuenta de Google). Los robots nunca llegan a Odoo.

**Costo:** plan **Zero Trust Free hasta 50 usuarios** (de sobra para D'CASA). Si algún día pasa
de 50: pago por usuario (≈ US$7 por usuario al mes, autoservicio; verificar precio vigente).
Al elegir el plan Free, Cloudflare puede pedir una tarjeta aunque no cobre.

**El problema a resolver:** el panel y la tienda viven en el mismo Odoo. Si se pone Access
sobre `/web` en `dcasapty.com`, se rompe la tienda (las fotos están en `/web/image`, el JS en
`/web/assets`) y el portal de clientes (`/my` entra por `/web/login`). Por eso el plan usa **un
subdominio solo para el panel**.

### Pasos exactos

1. **Subdominio del panel.** En `edge/wrangler.jsonc` → `routes`, agregar
   `{ "pattern": "panel.dcasapty.com", "custom_domain": true }` junto a `dcasapty.com`.
2. **Zero Trust.** Cloudflare › **Zero Trust** → elegir nombre del equipo (p. ej.
   `dcasa` → `dcasa.cloudflareaccess.com`) → plan **Free**.
3. **Cómo se identifican.** Zero Trust › Settings › Authentication: dejar **One-time PIN**
   (código al correo) y, si se quiere, agregar **Google** como proveedor.
4. **Aplicación.** Zero Trust › Access › Applications › **Add an application** › **Self-hosted**:
   - Dominio: `panel.dcasapty.com` (todas las rutas).
   - Política «Administradores D'CASA»: Action **Allow**, Include → **Emails** → los correos de la
     dueña y de quien administre. Duración de sesión: 24 h.
   - Opcional: exigir llave de acceso o MFA del proveedor (Independent MFA).
5. **En el Worker** (cambio de código pendiente, pequeño):
   - En `panel.dcasapty.com`: dejar pasar todo a Odoo (Access ya filtró) y **verificar** el JWT
     de Access (`ctx.access` o la cabecera `Cf-Access-Jwt-Assertion`) para que nadie lo salte.
   - En `dcasapty.com`: **redirigir `/odoo*`** (el panel) a `panel.dcasapty.com`. `/web/login` se
     queda, porque lo usan los clientes del portal; el borde no sabe si quien entra es cliente o
     personal, así que el personal entra siempre por `https://panel.dcasapty.com/odoo`. (Un
     empleado que entre por `dcasapty.com/web/login` termina en `/odoo` y lo redirige al panel,
     donde Access le pide identificarse.)
   - Desactivar `workers.dev` (`"workers_dev": false`) o protegerlo también con Access: si no, es
     una puerta lateral sin Access.
6. **Probar en staging** (`panel.staging.dcasapty.com`): entrar al panel, editar el sitio web
   (el editor abre el sitio dentro del panel), imprimir PDF, Brian en el panel.
7. **Encender en producción** y avisar al personal de la nueva dirección.

### Cómo convive con lo demás

- **Clientes y portal `/my`**: siguen en `dcasapty.com`, sin Access, con su clave de Odoo.
- **Socios `/socios`**: siguen igual (celular + PIN, con su propio candado y Turnstile).
- **Brian por MCP (`/brian/mcp`) y Telegram (`/brian/telegram/…`)**: se quedan en `dcasapty.com`,
  **fuera** de Access (Telegram no puede iniciar sesión en Access). Ya tienen su propia
  protección: clave de API por usuario, secreto del webhook y límites. Si algún día MCP se mueve
  detrás de Access, se usa un **Service Token** de Access para el cliente MCP.
- **Respaldo y tienda estática** (`/__edge/*`): siguen con su token, sin Access.
- **El doble factor de Odoo se mantiene**: Access es una capa más, no un reemplazo.

---

## 9. Referencia rápida de variables

| Variable | Valores | Por defecto |
|---|---|---|
| `DCASA_2FA_OBLIGATORIO` | `0` / `1` | `0` |
| `DCASA_2FA_ALCANCE` | `admins` / `internos` | `admins` |
| `DCASA_2FA_RESCATE` | login del usuario a rescatar (quitar después) | — |
| `DCASA_SESION_ADMIN_HORAS` | horas, `0` = sin cierre | 12 (al instalar) |
| `DCASA_INACTIVIDAD_ADMIN_MIN` | minutos, `0` = sin bloqueo | 60 (al instalar) |
| `DCASA_AVISO_LOGIN_TELEGRAM` | `0` / `1` | `1` |
| `DCASA_ROBOTS_IA` | `abierta` / `equilibrada` / `cerrada` | `equilibrada` |
| `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET` (secreto) | claves del widget | — (apagado) |
| `DCASA_TURNSTILE` | `off` = apagar | — |

Parámetros de Odoo relacionados: `base.login_cooldown_after` (5), `base.login_cooldown_duration`
(60), `dcasa_seguridad.bloqueo_tope_s` (1800).
