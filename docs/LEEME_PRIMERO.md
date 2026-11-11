# Léeme primero (para quien retome el trabajo)

Este archivo existe para que, cuando una sesión de trabajo se reinicie y el contexto se pierda, quien siga (una persona o
Claude) entienda **en cinco minutos** cómo se trabaja aquí, qué está hecho y qué sigue, sin empezar de cero ni preguntarle
a la dueña lo que ya se contestó. `CLAUDE.md` apunta aquí.

> **Regla de oro de este archivo:** al terminar cada sesión se agrega una entrada arriba de la
> [Bitácora](#bitácora-de-sesiones) (qué entró, qué quedó en staging, qué sigue) y se actualiza
> [PRIORIDADES.md](PRIORIDADES.md). Si no se anota, la próxima sesión no lo sabe.

## 1. Con quién se trabaja y cómo hablarle

- La dueña **no es técnica**. Se le habla en español sencillo y corto, de tú, sin jerga ni siglas sin explicar; se usa
  a cada persona se le trata como la persona misma diga; si no lo dijo, en neutro («la persona», «quien»), sin adivinar por el
  nombre. Primero el resultado, después el detalle.
- Lo que pide un **jefe** (el dueño de la empresa) llega a través de ella: se trata como pedido de la dueña, y se le
  responde a ella con lo que pueda reenviarle.
- **Corrección (2026-10-26):** el responsable del negocio es **hombre**; en este repositorio «la dueña» es solo el nombre
  de siempre para quien trabaja con Claude. En todo lo que se imprime o se firma (actas, cartas, papeles para los jefes)
  nunca «dueña» ni «dueño»: un cargo neutral y profesional («Gerencia general», «CEO», o «Aprobado por» con una línea de
  Cargo para que cada uno escriba el suyo). Al hablarle, en neutro si no lo dijo.
- **Nunca se pide un secreto por el chat** (claves, tokens, contraseñas). Se le dice *dónde* ponerlo (secreto de
  Cloudflare o de GitHub) y se confirma que quedó cargado sin ver su valor.
- **Los datos de personas** (nombres, correos, celulares, cédulas, facturas de clientes) viven solo en Odoo: ni en el
  repositorio, ni en documentos, ni en pruebas. Tampoco se guarda en GitHub un PDF de una entrega o factura real.
- **Seguridad y menos fallas antes que velocidad** (dicho por la dueña el 2026-10-16): no importa esperar las pruebas; importa no tener fallas ni huecos. Nunca recortar pruebas para ir más rápido.
- **Criterio contable:** cuando una cifra puede mostrarse de varias formas (con o sin ITBMS, etc.), se decide por mejor práctica contable y se explica en la etiqueta; la preferencia de la persona no manda sobre eso. Regla vigente: ventas, costo y ganancia sin ITBMS; el dinero que se mueve (por cobrar, cobrado, caja) con ITBMS.
- **Contactos:** la limpieza de duplicados es de **clientes y proveedores**; las fichas de usuarios y empleados del sistema se respetan.
- Si una respuesta le va a servir a otra persona (el jefe, la contadora), se entrega como documento en Claude Docs, no
  solo en el chat.

## 2. Autorizaciones (lo que se puede y no se puede hacer solo)

| Acción | ¿Hace falta su «sí»? |
|---|---|
| Programar, probar y subir a la rama de trabajo | No (autorizado de forma permanente) |
| Desplegar a **staging** | **Antes, capturas a la dueña y su visto bueno** (regla del 2026-10-17: capturas → su filtro → pruebas → staging → producción). Capturas con datos de prueba, en computadora y celular, revisadas antes de mandarlas |
| Crear el PR hacia `main` | Solo cuando lo pide o ya dijo «pásalo a producción» |
| Unir a `main` y desplegar a **producción** | Permiso general desde el 2026-10-17 («súbelo en cuanto vayas terminando») **para lo que ella ya vio en capturas** y pasó pruebas y revisión. Si el código cambia después de su visto bueno, se le avisa antes |
| Borrar datos, ramas, respaldos, secretos | Sí, y mirando primero qué se borra |
| Cifras de dinero, puntos, comisiones, impuestos | Nunca se inventan (ver `CLAUDE.md`: `puntos.json`, reglas de marca) |

## 3. Cómo se llega a producción (receta)

La receta completa, la que se usó en los despliegues 31 a 47, está en un solo lugar:
**[DESPLIEGUE.md › La receta de producción](DESPLIEGUE.md#la-receta-de-producción)**. En corto:

1. Cambio en la rama de trabajo con su prueba; en local, `scripts/test.sh <módulos>` (PostgreSQL local; si se cayó:
   `pg_ctlcluster 16 main start` y esperar la recuperación), `ruff check addons` y, si tocó un Worker, `npm test && npm run
   typecheck` en su carpeta.
2. **CI/CD** a mano en la rama con `desplegar_en = staging`: todas las pruebas y, si pasan, staging (unos **45 minutos**:
   ~25 de pruebas de Odoo y ~20 del despliegue a staging, CI #260 del 2026-11-05).
3. Con staging sano y el «sí» de la dueña: PR con `[skip ci]` en el título, *squash* con `expectedHeadSha` = el commit
   probado, y comprobar que el árbol de `main` es el del commit probado.
4. **Desplegar** desde `main` a `production` con el `imagen_digest` y el `app_version` probados: **`app_version` es el
   SHA de 40 de la rama que construyó el CI, nunca el del *squash*** (se repitió en Desplegar 55), y
   `respaldo_previo = true`: unos **15 minutos**, contando los 600 s de vigilancia del final (`esperar_salud.sh`).
5. Mirar `/dcasa/salud`, avisarle a la dueña qué cambió para ella (sin tecnicismos), cancelar el CI que abrió el PR y
   traer `main` a la rama con `git merge -s ours origin/main`. **Desplegar Juan** solo si cambió `juan/`.

## 4. Trampas ya conocidas (no volver a tropezar)

- **«Sano» no es «Odoo contesta» (incidente 1 del 2026-10-16, en CONTEXTO_AGENTICO).** El arranque decidía actualizar la base solo
  por la variable `APP_VERSION`, que puede llegar atrasada, y el despliegue daba por sano cualquier 200: producción
  quedó con el código nuevo sobre la base vieja (o con la imagen vieja) y el Inicio y otras pantallas fallaron. Ahora
  la imagen sabe su commit y la huella de su código, actualiza la base si no coinciden y el despliegue exige
  `version` y `base_al_dia` (ver `docs/DESPLIEGUE.md`). Después de cada despliegue igual se abre el Inicio.
- **`app_version` tiene que tener imagen en el registro.** El despliegue usa la etiqueta `dcasa-odoo:<app_version>`,
  que solo existe para los commits que construyó el CI (el de la rama, no el del *squash* en `main`). Con otro SHA
  falla con `IMAGE_REGISTRY_DOESNT_CONTAIN_IMAGE`, y aun así el Worker nuevo ya quedó activo (Cloudflare activa el
  Worker antes que la imagen).
- **Nunca inventar un SHA** (ni "completar" uno corto): se lee del PR o del run. Ya falló un merge por eso.
- `rerun_failed_jobs` da 403 mientras el run sigue en curso: esperar a que termine. Una prueba que falló en CI no se
  "pausa": se espera o se cancela el run y se corrige.
- Los botones de la cabecera de una lista llaman al método con la lista de ids (vacía si no hay selección): un método
  `@api.model` fallaría. Hay un test guardián en `dcasa_base/tests/test_superficie_rpc.py`.
- PyPDF2 reescribe los textos de un PDF fusionado con escapes octales; las pruebas de PDF usan `textos()` que los
  decodifica (`dcasa_invoice/tests/test_paquete.py`).
- Las variables del Worker (`VARIABLES_DEL_CONTENEDOR`) llegan al contenedor al arrancar: un cambio en el panel de
  Cloudflare se aplica al reiniciar o en el siguiente despliegue. Los IDs (p. ej. `BRIAN_TELEGRAM_CHATS`) son variables
  normales, no secretos.
- Las pruebas de Odoo tardan ~25 minutos en CI y el ciclo completo con staging ~45; un fallo cuesta un ciclo entero.
  Antes de subir, correr en local los módulos que se tocaron.
- El CLI `gh` existe en esta máquina y sirve para **leer** (runs, tiempos de cada job, issues). Lo que **escribe** en
  GitHub (PR, unir, lanzar flujos, comentar) va por las herramientas `mcp__github__*`.
- Cada función nueva de la plataforma debe poder usarla Brian (`docs/BRIAN.md`); el PR lo pregunta.

## 5. Dónde está cada cosa

| Quiero saber… | Voy a… |
|---|---|
| Qué falló antes, por qué y cómo se arregló (incidentes, despliegues, CI, trampas) | [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md) |
| A qué versión segura volver si algo se rompe, y cómo | [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md) |
| Qué se pidió y en qué orden se hace | [PRIORIDADES.md](PRIORIDADES.md) |
| Cómo está todo hoy y qué le toca decidir o hacer a la dueña | [PRIORIDADES.md](PRIORIDADES.md) (estado del día y «Lo que falta de la dueña») |
| Trabajo de desarrollo abierto | Los issues del repositorio (`mcp__github__list_issues`) |
| Cómo se despliega y se vuelve atrás | [DESPLIEGUE.md](DESPLIEGUE.md) (la receta) y [OPERACION.md](OPERACION.md) |
| Juan: cómo funciona, la bandeja y los canales | [JUAN.md](JUAN.md) · [JUAN_ODOO.md](JUAN_ODOO.md) · [JUAN_CANALES.md](JUAN_CANALES.md) |
| Qué ve cada rol | [PERMISOS.md](PERMISOS.md) |
| Cómo hablar con Brian y qué puede hacer | [BRIAN.md](BRIAN.md) |
| Todo lo demás | [README.md](README.md) (índice de `docs/`) |

## Bitácora de sesiones

> Más reciente arriba. Cada entrada: fecha, qué quedó en producción (con el commit), qué quedó solo en staging, qué
> sigue. Se guardan las diez más recientes; las viejas se resumen en una línea abajo y su texto completo pasa a
> [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md).

### 2026-11-11: versión estable 4; Instagram con fotos confirmado; enlace de choferes encendido; cierre de semana

**En producción** (sin despliegues nuevos de Odoo): Odoo y el borde en Desplegar 63 (`3e2ccfc`) y Juan en Desplegar
Juan 20 (`c378382`). Este día solo se registró la versión estable, se ordenó la documentación y se cerraron issues.

- **Versión estable 4** (pedido de la dueña: «actualizar esta versión como la última versión estable»): Desplegar 63
  (imagen `sha256:acda72c1…`, `app_version` `3e2ccfc`) con Juan hasta Desplegar Juan 20. En `.github/versiones_estables.json`,
  en el botón «Volver a una versión estable» y en [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md), con la nota de que
  Juan se vuelve aparte. **Ensayada en staging** con el botón: run 42951600639, bien en unos 24 minutos.
- **Instagram con fotos, confirmado por la dueña** (Juan 20: la foto se sube en el mismo envío, como Messenger).
  **Enlace para choferes encendido** por la dueña.
- **Issues cerrados** (resueltos según la dueña el 7 nov): #9, #10 y #12 (códigos de barras) y #26 (topes de Brian).
  Quedan 10 abiertos (privacidad #22 y #23, Juan #24, CRM fase 2 #15 y #17 a #21, puerta `/master` #27).
- **Evaluación pedida por la dueña:** 82/100 «en producción de verdad». Para subir a 90+: avisos a Gerencia cuando un
  canal de Meta deja de enviar o recibir (el 131070 no avisaba), la IA de respaldo de Juan (`ANTHROPIC_API_KEY`
  falta, según `/salud`), plantillas de WhatsApp y nombre visible, privacidad (#22 y #23).
- **Dependabot #98** (Juan: `ai` 7.0.164 y `@ai-sdk/*`, versiones de parche) queda abierto a propósito: no se
  despliega Juan al cierre de la semana sin nadie mirando. Va primero la semana que viene.
- **Sigue:** ver [PRIORIDADES.md](PRIORIDADES.md) «Lo que sigue».

### 2026-11-10: WhatsApp 131070 RESUELTO («redireccionar conversación» a D'CASA Juan); Juan pide el control y anota todo

**Resuelto (10 nov, tarde):** con la cuenta de los jefes (administradores del portafolio DCasa Pty), la dueña encontró en
Meta el botón **«redireccionar conversación»** (el Enrutamiento de conversaciones), mandó las conversaciones a «D'CASA
Juan» y **eliminó a Callbell**. WhatsApp volvió a enviar y recibir sin esperar los 7 días que decía soporte.

**En producción** desde el 2026-11-10: PR #104, CI #315, **Desplegar Juan 17** (`main` = d40607f, árbol = cf52548);
PR #105, CI #317, **Desplegar Juan 18** (`main` = ac75436, árbol = 4c16cd2); y PR #106, CI #319, **Desplegar Juan 19**
(`main` = f8a6c24, árbol = b955b2f); y PR #107, CI #321, **Desplegar Juan 20** (`main` = c378382, árbol = f1cba72).
Odoo sin cambios.

- **Instagram conectado** (10 nov, tarde) por la página DCASA PTY, con la misma app y la misma llave que Messenger
  (`META_PAGE_TOKEN` reemplazada; Messenger siguió funcionando). Juan contestó un DM de prueba y salió en Odoo con el
  nombre. La foto no salía (igual que Messenger el 9 nov). **Juan 19** la subía aparte (`attachment_id`) y siguió
  fallando; **Juan 20** la sube en el mismo envío como Messenger y, si falla, Odoo muestra lo que dijo Meta a cada intento.
  **Confirmado por la dueña: la foto llegó por Instagram.**
  Se descartó la guía de un conocido («inicio de sesión con Instagram»): otra llave que vence y cambios en Juan.

- **La causa más probable del 131070**: el **«Enrutamiento de conversaciones»** de Meta (Conversation Routing, desde
  septiembre de 2026) decide qué app es la principal de los chats del número; solo esa contesta y las demás reciben
  131070. Al quitar Callbell, Meta **no nombra otra principal** por su cuenta. Ver [JUAN_CANALES.md](JUAN_CANALES.md) §1.
- **Juan 17:** si un envío da 131070, Juan pide el control de ese chat (Thread Control, «take») y, si Meta se lo da,
  manda otra vez lo rechazado. Todo envío rechazado deja su código y su `fbtrace_id` en el registro de `dcasa-juan`.
  **Juan 18:** un aviso de WhatsApp que no da mensaje ni palomita se anota con su forma (campo, claves, tipos), sin datos.
- **Pruebas con soporte de Meta (chat):** a las 12:13 un envío desde el Explorador de la API Graph (app «D'CASA Juan»,
  número de la tienda) **llegó** al celular: **ya se puede enviar**. Los mensajes al número llegan (doble palomita) pero
  no a Odoo. Se volvió a suscribir la app a la WABA (`POST 1313438470854835/subscribed_apps` → `success: true`) y a las
  12:22 Meta sí llamó al webhook (200), pero el mensaje no apareció en Odoo (Juan 18 dirá qué forma tiene ese aviso).
- **Soporte de Meta:** tras un cambio de proveedor, el número tarda **hasta 7 días** en desvincularse de la app y del
  activo anterior (desde el 9 nov: hasta el **16 nov**). **Callbell** propuso eliminar el número y volver a
  registrarlo: **no se hace** (se pierde límite, calidad y plantillas; hace falta la SIM y quizá el PIN de dos pasos).
  Se le pidió a Callbell quitar sus enlaces y decir si puso PIN. Los jefes ya entraron como administradores del
  portafolio: queda una revisión con Claude en Chrome del enrutamiento, socios y apps conectadas (cambios solo con «sí»).
- **Sigue:** WhatsApp, Messenger e Instagram funcionan con fotos (el 131070 se resolvió el mismo 10 nov). El enlace
  de choferes ya está encendido (11 nov). Pendiente: el motivo real en «Quedó por enviar», pedir un nombre visible
  nuevo de WhatsApp («DCasa Pty» DECLINED) y, si la dueña lo pide, respuestas a comentarios de Instagram.

### 2026-11-09 (tarde y noche): enlace para choferes; «Colchones» abre WhatsApp; Messenger conectado; WhatsApp bloqueado por Meta (131070)

**En producción** desde el 2026-11-09: PR #100, CI #305, Desplegar 63 (imagen `sha256:acda72c1…`, versión 3e2ccfc) y
Juan 13 (`main` = 4a01039, árbol = 3e2ccfc).

- **Enlace para choferes** (pedido de la dueña: «un link de calculadora a los choferes … que no vean la tabla de
  kilometraje»; «un solo enlace para todos»). En Envíos › Tarifa, abajo, Gerencia lo enciende, copia el enlace y lo
  cambia con «Crear un enlace nuevo». El chofer busca el lugar y ve solo el nombre, la zona, el precio **desde D'CASA**
  y la ruta en Google Maps; nunca los km ni la tabla; sin tarifa aprobada, «confirma el precio con la tienda».
  **«Usar mi ubicación» viene apagado** («por defecto inamovible … que nosotros lo decidamos»): solo Gerencia lo
  enciende. Ver [ENVIOS.md](ENVIOS.md) «Enlace para choferes». La dueña **lo encendió el 11 nov**.
- **Revisión de seguridad independiente** del enlace: nada bloqueante; se arreglaron los límites (2 búsquedas a la
  vez, 1 500 por día con nota a quien creó el enlace y contador en la ficha, IPv6 por /64, 300 por minuto entre todos,
  texto corto), cuerpos rotos que daban 500, `write` sin permiso que rearmaba el buscador, `create` que aceptaba el
  secreto y el borde que no reconocía el enlace con idioma delante. Lo no evitable (quien tiene el enlace ve precios
  y Google Maps los km) quedó escrito en ENVIOS.md.
- **Portada:** una categoría sin nada publicado (hoy «Colchones») abre WhatsApp con «quiero información de
  colchones»; al publicar un colchón vuelve sola a la tienda (decisión de la dueña). Confirmado en producción.
- **Dependabot** #96, #97 y #98 (Juan: `ai` y `@ai-sdk/*`; borde y puente: `workers-types` y `wrangler`).
- **CI:** la 303 falló en la prueba de «Colchones» (el catálogo del CI ya trae colchones publicados) y la 304 en una
  prueba del puente que dependía de la velocidad de la máquina; las dos reproducidas en local y arregladas (ver
  CONTEXTO_AGENTICO).
- **Messenger conectado** (con Claude en Chrome y la dueña): control total de la página para la cuenta usada, webhook,
  suscripciones solo en DCASA PTY y `META_PAGE_TOKEN`. Juan contestó un «Hola buenas» y la conversación salió en Odoo.
  Hasta la revisión de Meta (que pide verificar el negocio: lo ve la administración) solo contesta a quien tiene rol en
  la app. **Instagram** quedó a medias: «Invalid Scopes» (faltan los permisos de Instagram en la app) y hace falta
  entrar con acceso al portafolio DCasa Pty. Pasos en [JUAN_CANALES.md](JUAN_CANALES.md) §3.
- **WhatsApp dejó de enviar desde las 16:00** con el código **131070** («otra app controla la conversación»). No fue el
  token de la página ni el sistema (Messenger funcionó de punta a punta a la misma hora): en Meta el número quedó
  **sin cuenta de mensajes** («Add a Messaging account»), probablemente porque Callbell retiró la suya cuando se le pidió
  retirar su línea de crédito. Lo arreglan los dueños en Meta desde DCasa Pty (crear y ligar una cuenta de mensajes con
  su tarjeta). Ver JUAN_CANALES §1 «Si deja de contestar».
- **Fotos de Messenger** (madrugada del 10): el texto salía y la foto no («(#100) Error al subir el producto»: Meta no
  lograba bajarla de nuestra URL). Juan ahora sube el archivo a Meta (multipart `filedata`), con respaldo por URL. En
  producción: PR #101, CI #308, **Desplegar Juan 14** (`main` = 4cc4b97, árbol = 3af9123; Odoo sin cambios).
  **Confirmado** por la dueña: la foto de la cama llegó por Messenger con su texto.
- **El nombre del cliente de Messenger e Instagram** (en Odoo salía «Messenger 2838…»): Juan se lo pide a Meta una vez
  por conversación antes de guardar el mensaje; Odoo cambia el nombre provisional por el real. En producción: PR #102,
  CI #310, **Desplegar Juan 15** (`main` = 7707b53, árbol = 5d19c7c).
- **Sigue:** que los dueños liguen la cuenta de mensajes (y probar que Juan vuelva a enviar; si sigue el 131070, el
  «Agente de negocios de Meta»); encender el enlace de choferes; Instagram;
  en el próximo lote, el motivo real en el aviso «Quedó por enviar».

### 2026-11-09: «No llegó» por el pago de Meta (131042); preguntas sin respuesta para las vendedoras; videos con voz

**En producción** desde el 2026-11-09: PR #99, CI #301, Desplegar 62 (imagen `sha256:f467a09a…`, versión 5882fa4) y
Juan 12 (3b86ee3).

- **«No llegó» desde hace dos días** (WhatsApp oficial; «a veces sí, a veces no»). **Causa:** el globito de la
  etiqueta dice **131042, «Business eligibility payment issue»**: Meta no deja salir los mensajes por un problema de
  **pago de la cuenta de WhatsApp Business**, no del sistema ni de la IA. En Facturación y pagos › Cuentas de mensajes
  la cuenta del número (la que era de **Callbell**, ID …764382) se pagaba con una **línea de crédito de Callbell**; la
  dueña dejó Callbell y conectó Juan con el mismo número. Las otras dos «DCasa Pty» no tienen método de pago. **Lo
  arregla la dueña en Meta** (tarjeta propia y predeterminada en esa cuenta; si no la deja, pedirle a Callbell que
  revoque la línea; información fiscal). Se le dio un encargo para Claude en Chrome que revisa todo en solo lectura y
  trae un reporte. Lo ya fallido no se reenvía solo: las vendedoras vuelven a escribirles.
- **En el sistema** (la revisión de estos cambios, más abajo): los motivos de la cuenta (131042 pago, 131031 bloqueo, 131048 spam)
  en palabras de la tienda y con su código siempre entero; **aviso por Telegram a Gerencia** (cron
  `ir_cron_avisos_de_cuenta`, una vez cada 6 h por código, reintento a la media hora si no le llegó a nadie; los
  recibos de más de 2 h no avisan; también un rechazo al enviar). Ver [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md)
  «WhatsApp oficial (Meta)».
- **Preguntas sin respuesta para las vendedoras** (pedido de la dueña): menú para Ventas y botón **Contestar**. Sin
  cifras ni política (dinero, números también en palabras, plazos, horarios, garantía, entregas, crédito, cambios,
  descuentos…; `conocimiento_texto.necesita_revision`, por raíces), Juan la usa al momento; con eso, Gerencia la revisa
  («Convertir en conocimiento», borrador). El tema es editable y se limpia; la pregunta del cliente también se revisa
  (un «sí» no confirma un precio que el cliente inventó). La dueña no alcanzó a elegir: se usó la opción recomendada.
  **Revisión adversarial independiente** (dos pasadas): un bloqueo (el precio de la pregunta en el título) y varias
  cosas a mejorar, todo arreglado con su prueba.
- **Videos:** a los 3 de camas (805, 801, Queen Black) y a los 3 del lanzamiento de la página se les puso la voz de
  Yuli (ElevenLabs v4) y música de Suno pedidas al **Calendario de Marketing** por MCP (≈ $0.66 en total), pegadas por
  frase con ffmpeg y revisadas con un reconocedor de voz (vosk). El calendario no tiene herramienta para subir archivos
  ni para leer los medios de una publicación: la dueña subió los videos a mano a los días 11, 13 y 15 de noviembre.

### 2026-11-07 (3): Camila: «Abrieron» y «Tocaron» en 0; remitente propio de las campañas y aviso de Resend, en producción

- La tabla de campañas decía 0 «Abrieron» y 0 «Tocaron». **Causa:** Resend trae el conteo de aperturas y clics
  apagado por dominio y Camila salía del remitente de las facturas (`ventas@dcasapty.com`); encenderlo ahí pondría el
  píxel y cambiaría los enlaces de las facturas. **Decisión** ([CAMILA.md](CAMILA.md) §1d): un subdominio de
  marketing (`novedades.dcasapty.com`, seguimiento `links`) con el conteo encendido; las facturas, limpias.
- **«Remitente de las campañas»** (al final de Camila; Gerencia y administradores; `dcasa_camila.remitente`): vacío =
  el de las facturas (nada cambia hasta que se ponga). El *broadcast* y «Enviarme una prueba» salen de ahí con el
  nombre «D'CASA Panamá» y la respuesta a `info@dcasapty.com` de siempre. El remitente de las facturas no se tocó.
- **El aviso:** con la clave de campañas y en producción, Camila lee `GET /domains` (y el detalle) cada 6 horas con el
  cron, al guardar el remitente, con «Revisar ahora» y al tocar «Enviar». Sin verificar o sin estar en Resend: lo dice
  y **no deja enviar**; con el conteo apagado: «Resend no está contando … de este remitente: Abrieron y Tocaron saldrán
  en 0» con los tres pasos. La pantalla solo lee lo guardado (nunca llama a Resend ni se cae por él); si Resend falla,
  una nota suave. Debajo de la tabla: las enviadas sin conteo siempre dirán 0. La Guía: «¿Por qué Abrieron sale en
  0?». Brian lo dice en `estado_campanas`.
- Pruebas (primero en rojo sobre el código de antes: 3 fallas y 34 errores): `test_remitente.py` (28, dos en el
  navegador: el aviso arriba, la nota, **la pantalla baja hasta el final** en computadora y celular sin scroll de lado,
  Gerencia cambia el remitente) y `test_resend.py` (+1). Todo `dcasa_camila` en base nueva: 238 en verde (en dos
  tandas); la lista blanca de RPC revisada por `odoo-bin shell` (vacía); `ruff` limpio. De `dcasa_guia`, 3 pruebas
  del buscador fallan en esa base angosta porque no tiene `dcasa_nomina` («planilla», «seguro-social»): no es de este
  cambio. Capturas con datos inventados en el scratchpad de la sesión (`capturas_camila_remitente`).
- **Sin push, PR ni despliegue.** Falta de la dueña ([CAMILA.md](CAMILA.md) §6b): agregar y verificar
  `novedades.dcasapty.com` en Resend (DNS en Cloudflare, nube gris), encenderle el conteo con `links`, y poner el
  remitente en Camila. Si la prueba no sale desde el subdominio, la clave de las facturas está limitada a un dominio en
  Resend › API Keys.
- **En producción:** PR #95 (`main` = `848d314`, árbol = `e53e5d8`), **Desplegar 61** sano y confirmado 19:00 UTC
  (versión `e53e5d8b4ebf`) y **Desplegar Juan 11** (`848d314`, que además quita el tope de 20 notas de voz al día a pedido
  de la dueña). La dueña dejó `novedades.dcasapty.com` verificado en Resend con «Auto configure» de Cloudflare y el conteo
  de aperturas y clics encendido en `links.novedades.dcasapty.com`.

### 2026-11-07 (2): issues #24 (Juan) y #25 (Conversaciones), lo que quedaba, en producción

- La dueña aprobó el 2026-11-07 los pendientes de los dos issues, primero lo que ve el cliente. **Sin push, PR ni
  despliegue**: cuando toque, **Odoo primero y después Juan** (Juan no depende del Odoo nuevo; la integración sí espera
  el Odoo nuevo).
- **Juan** (cada uno con su prueba, primero en rojo; `cd juan && npm test`: 1.223, `typecheck` limpio):
  1. **Eco de Messenger e Instagram**: lo que sale se anota antes de enviar (`vuelo:*`); el eco ya no calla al bot 120 min
     (`eco-meta.test.ts`, 4 de 7 en rojo).
  2. y 3. **Notas de voz**: «quiero hablar con alguien» o «no me escriban» en audio valen como escritos; no se transcribe
     ni se lee una imagen en descanso, con un repetido ni pasado el tope diario (`nota-de-voz.test.ts`, 7 de 8). El tope
     de 20 notas de voz por persona al día que entró aquí **se quitó** el mismo día a pedido de la dueña («le agrada que
     pueda responder notas de voz»): queda solo el tope diario general.
  4. **Reintento del turno**: la corrección recibe su ronda de herramientas y la pasada sin herramientas lo consultado; la
     misma escritura con los mismos argumentos va a Odoo una vez por turno, `pasar_a_vendedora` una vez, tope de 8
     (`reintento-del-turno.test.ts`, 4 de 6; y una con el SDK real de Claude).
  5. **Seguimiento**: se reclama antes de redactar y se vuelve a mirar al cliente justo antes de enviar
     (`seguimiento-carrera.test.ts`, 4 de 6).
  6. **Menores**: registros sin claves ni tokens; `{{LECCIONES}}` con función (`menores-ronda8.test.ts`, 3 de 3).
- **Conversaciones** (`tests/test_ronda8_conversaciones.py`, 20 de 23 en rojo antes; Sofía, 2 nuevas en rojo antes):
  atraso máximo de un seguimiento (**ajuste nuevo, 6 h**: lo vencido se salta con una nota, no sale de golpe), nada de
  «¿sigues interesado?» tras un traspaso que nadie atendió (`traspaso_sin_atender_desde`; Sofía lo pone en «Contéstale»,
  que antes NO cubría ese caso), seguimiento por persona (solo el canal por donde escribió último) y «No contactar» que
  sigue a la persona al cambiar de ficha, un «descartado» tardío ya no cierra el ciclo nuevo, notas sin repetir en la
  oportunidad, el mantenimiento purga los borradores de Telegram y la zona con número de casa o apartamento no se guarda.
  En local, base nueva: `dcasa_conversaciones` 1.253 pruebas en dos mitades (solo las 2 referencias visuales a 390 px
  que ya fallaban en esta máquina), `dcasa_sofia` 72, integración real de Juan 39 de 40; `ruff` limpio.
- Cambió una prueba vieja con razón: `test_no_pide_fuera_de_horario_aunque_ya_toque` usa un atraso de 4 h (con 8 h ahora
  se salta) y la integración `seguimiento.ts` espera que el «descartado» no cierre el ciclo nuevo (esperaba el hueco).
- Lo que no cubre: las conversaciones que hoy ya esperan a una persona tras un traspaso no quedan marcadas (sin
  migración: la marca empieza con el próximo traspaso). Quedan del #24 tres menores fuera de lo aprobado.
- **Revisión adversarial** (10 hallazgos, todos arreglados con prueba; `9c00c16` Juan, `dfeb5ee` Odoo y Sofía): un rechazo de
  `pasar_a_vendedora` ya no frena la llamada corregida (tampoco en el mismo paso); el reclamo del seguimiento es de quien lo
  puso y se mira la tabla `seguimientos` justo antes de enviar; las notas de voz y fotos de una vendedora no gastan los topes
  del cliente; prueba de la corrección con Meta. En Odoo: «espera a una persona» frena el seguimiento una semana como mucho, se
  ve en la conversación y se quita con **«Ya la atendí»**; por persona solo cuentan las hermanas que podrían hacer el
  seguimiento (un «hola» por otro canal ya no deja a nadie sin ninguno) y uno en camino por otro canal pospone, no borra;
  solo se salta lo programado antes del límite (`seguimiento_programado_en`: «Crear oportunidad» al día siguiente sale) y,
  si el siguiente también venció en la caída, también se salta (antes salía en la misma vuelta); «el cliente pidió que no lo
  contacten» marca No contactar; la dirección exacta tampoco queda en `brian.accion`; un «Contéstale» descartado no vuelve
  con cada mensaje mientras siga marcada. Pruebas: Juan 1.230 (`typecheck` limpio); Odoo, clases tocadas 125 + API,
  superficie RPC y vecinas 128, 0 fallas (las 3 nuevas de atrasos y Sofía, en rojo antes); `ruff` limpio. No se corrió
  `dcasa_conversaciones` entero ni la integración real de Juan (la integración escribe `seguimiento_proximo` a un minuto:
  no la toca el atraso).

### 2026-11-07 (1): citas, reenviados, reacciones y palomitas en el chat, en producción

- Pedido de la dueña: «El chatbot de D'Casa no tiene citas, reenviados, reacciones ni "entregado/leído"… si un cliente
  dice "este", seleccionando un mensaje… solamente vemos la palabra "este"… no vemos el estado del mensaje.»
- **En la burbuja** ([JUAN_ODOO.md](JUAN_ODOO.md) › «La conversación»): el recuadro de la **cita** sobre el texto (quién
  lo dijo: Tú, Juan, la vendedora o Cliente; dos líneas; «Foto», «Audio»… sin texto; un clic lleva al original;
  «Mensaje que no está en el historial» si es viejo), **«Reenviado» / «Reenviado muchas veces»**, la **reacción** del
  cliente en la esquina (una nueva reemplaza, quitarla la borra) y las **palomitas** (✓ gris, ✓✓ gris, ✓✓ azul, ⚠ «No
  llegó» con el motivo) en vivo, por el mismo bus de siempre (un aviso liviano `recibos`, sin texto ni emoji).
  **«Responder»** en los mensajes del cliente (mouse o Tab; en el celular, dedo apretado): sale citado por WhatsApp
  (`context`) y Telegram (`reply_parameters`); sin id del canal, sale sin la cita.
- **Juan entiende «este»**: lo citado le llega a la IA como `[El cliente responde a este mensaje de D'CASA: «…»]`, un dato
  del cliente (neutralizado, tarjetas tapadas, 300 letras; el cliente no puede escribir la marca) y la regla 6 del prompt
  lo dice. Lo busca en su memoria (ahora cada burbuja guarda su `wamid`) o se lo completa Odoo en la respuesta de
  `/mensaje`. Un reenviado también lo sabe.
- **Datos:** `dcasa.mensaje` con `cita_id`/`cita_id_canal`/`cita_texto`, `reenviado`, `reaccion(_en)`, `estado_canal` y
  sus horas; modelo nuevo `dcasa.mensaje.parte` (el `wamid` de cada burbuja nuestra, su estado y su reacción). Ruta nueva
  `POST /dcasa/juan/v1/eventos` (palomitas y reacciones en tandas). Solo escribe el sistema.
- **Palomitas y reacciones no son mensajes del cliente**: no despiertan a la IA, no pasan por el Durable Object, no
  tocan último mensaje, «sin leer», seguimientos, ventana de 24 h, reparto ni Sofía, y no avisan a nadie.
  **A Meta se le contesta 200 aunque Odoo esté caído** para un aviso de solo palomitas (perder una palomita no es perder
  un mensaje; un 500 haría reenviar el lote por horas): se reintenta lo que cabe en `waitUntil` y lo que Odoo aún no
  conoce se vuelve a mandar a los 5 y 10 s. Los mensajes se siguen guardando antes del 200 (Desplegar 49).
- **Arreglado de paso:** WhatsApp oficial reenviaba la primera burbuja si se caía a la mitad de una respuesta (ahora
  `EnvioParcialError`, como Telegram).
- **Orden de despliegue: Odoo primero y después Juan.** Juan nuevo con Odoo viejo: Odoo ignora los campos nuevos y
  `/eventos` da 404 (Juan no insiste). Juan viejo con Odoo nuevo: igual que antes. Telegram: las reacciones necesitan
  volver a registrar el webhook con `allowed_updates` ([JUAN_CANALES.md](JUAN_CANALES.md) §2). Puente QR y
  Messenger/Instagram: no (el puente no pasa esos datos).
- Pruebas: Juan 1242 en verde (51 nuevas, con las del almacén de la pantalla; contra el código de antes, 44 en rojo y 7 guardianes que ya se cumplían);
  Odoo `test_citas.py` (29) y `test_panel_citas.py` (5 con Chrome: burbuja, «Responder», en vivo, rueda y marca, dedo a
  390 px; más las capturas): 32 de 34 en rojo con el código de antes, todas en verde ahora; el resto de
  `dcasa_conversaciones` en verde salvo las dos referencias visuales que ya fallaban en esta máquina (ver
  CONTEXTO_AGENTICO). Capturas para la dueña en el scratchpad de la sesión (`capturas_citas`), con datos de prueba.
- **Revisión adversarial, arreglada en la misma rama:** S1 «este» citando burbujas distintas ya no es spam (el anti-spam
  compara texto + id citado); S2 un PIN ya no sobrevive dentro de la cita (sin copia si lo citado está en la memoria de
  Juan; `redactar` limpia la copia que vino de afuera); S3 las marcas `[El cliente responde…]` y `[Vendedora]` no se
  imitan con invisibles, espacio duro, ancho completo, cirílicas ni letras delante, y las «» de lo citado pasan a “”; S4
  (Ley 81) Odoo ya no copia lo citado que está en el historial y borrar un mensaje lo limpia de las respuestas y de su
  chatter (la memoria de Juan es aparte: [JUAN_ODOO.md](JUAN_ODOO.md) › Privacidad); S5 un «leído» sube las burbujas y
  los mensajes anteriores (las palomitas azules ya salen en respuestas de varias burbujas); S6 «Responder» es solo el
  ícono en la computadora (el hilo ya no se corre de lado a 768 px); más los menores (tipos en el webhook, reenvío sin cita
  solo con 400 y código 100 o 131009, tandas de 100, *savepoint* por aviso, sin sustitutos sueltos ni bidi, el eco conserva
  la cita, temblor del dedo, horas en vivo, gris 3,8:1). Pruebas: Juan 1300 y `typecheck` (24 nuevas en rojo antes); Odoo
  `test_citas.py` 40 y `test_panel_citas.py` 9 (14 nuevas y 2 cambiadas: 15 en rojo antes), y 443 de las clases vecinas
  en verde salvo las dos referencias visuales a 390 px de siempre.
- **Sigue:** capturas a la dueña → su visto bueno → CI y staging → producción (Odoo y después Juan).
- **En producción (las dos entradas de hoy juntas):** PR #94 (`main` = `6d5dc8b`, árbol = `274f13d`), **Desplegar 60**
  sano y confirmado 06:58 UTC (versión `274f13dff3ee`) y después **Desplegar Juan 10** (`6d5dc8b`). Comentarios en los
  issues #24 (sigue abierto por tres menores) y #25 (cerrado). El contenedor de la sesión se reinició cuatro veces esa
  noche: los agentes se reanudaron o se rehicieron desde lo que dejaron en sus *worktrees* sin perder trabajo.

### 2026-11-06 (9): Camila etapa 1b: la lista de las novedades crece sola (se activa al agregar el correo), en producción

- La dueña vio «0 clientes con permiso» de unos 3,000 y no quiere marcar a nadie de golpe ([CAMILA.md](CAMILA.md) §1c).
  Primero se hizo una pregunta «Sí / No» en cada venta y Juan preguntando por WhatsApp (commit `55a6f4b`); ese mismo
  día la dueña cambió el diseño: «en el momento en el que se añade un correo, ya debe activarse automáticamente».
- **Se activa sola** al crear la ficha con correo, al agregárselo o cambiarlo, con «Guarda sus datos» de Sofía y
  cuando Juan guarda el correo que escribió el cliente: origen honesto «Se activó sola al agregar su correo» (nunca
  «tienda»), con quién; la ficha lo dice hasta que una persona toca «El cliente dijo que sí». Nunca con baja o «no
  contactar» del correo en cualquier ficha, después de un «no», importando, en bloque, instalando, por el sistema
  (`SUPERUSER_ID`), desde la web pública o el portal, y nada hacia atrás. El «no» queda anotado (cuándo, dónde, quién)
  y con él ya no se activa sola.
- **Al confirmar una venta o registrar un pago desde la pantalla**, la casilla sale ya activada con su correo (si el
  cliente dijo que no, se desactiva: queda el «no»); sin correo, «Sí / No» y lo pide. Sale DESPUÉS de confirmar o
  pagar y solo con la marca de los botones: nunca traba la venta ni el pago. No vuelve a salir en 180 días (ajuste
  `dcasa_camila.dias_entre_preguntas`).
- **Juan** nunca las activa: `guardar_correo` (el correo que escribió el cliente; le avisa que le llegarán y que
  puede decir que no) y `no_quiere_novedades` (siempre honra un no). `permiso_correo` en `/mensaje` y `/estado`:
  «activo» o «sin_correo». El pie de cada campaña: «Te llega porque nos diste tu correo en D'CASA. ¿No quieres más?
  Date de baja aquí».
- La pantalla de Camila cuenta por camino. Pruebas: `test_etapa1b.py` (primero en rojo sobre el código de antes) y
  `juan/test/dcasa/permiso-correo.test.ts` (3 de 5 en rojo).
- **Revisión adversarial** (2 que frenaban y varios a arreglar, todos con su prueba): el cron de Sofía ya no vuelve a
  suscribir ni borra un «no» (solo un acto explícito lo borra); la carga del sistema anterior, fusionar fichas,
  empleados, proveedores, el chatter y la creación rápida no activan nada (la activación es **por invitación**: solo
  la pantalla, Sofía y Juan); desmarcar con el correo en el mismo guardado es un «no»; «venía activada» en la venta
  es un origen aparte (nadie le preguntó); `flush_all()` antes de cada savepoint (un error de la venta no se traga);
  el cuadro no se cierra con Escape, el plazo cuenta desde que sale, uno viejo no le gana a un «no», cada quien ve
  solo los suyos y la casilla va en el azul de la marca.
- **Segunda revisión** (nada frenaba; arreglado en la rama, cada uno con su prueba): el enlace «Sí, quiero» después
  de un «no» sí lo anota (es un acto explícito); `cr.flush()` en vez de `env.flush_all()` antes de cada savepoint
  (también los precommit de quien llama); una empresa nueva, un correo con baja o un correo borrado ya no anotan un
  «no» que nadie dijo (en una empresa la casilla es de solo lectura); con un «no» viejo, marcar junto con un correo
  nuevo es un «sí» de una persona; desmarcar cuando el correo solo cambia de mayúsculas es un «no»; Juan recibe
  «sin_permiso» (tiene correo pero no le llegan) para que siempre sepa que un «no» se honra.
- **En producción:** con las dos revisiones adversariales, PR #92 (`main` = `cb541f8`, árbol = `8f3cdc3`), **Desplegar
  58** sano y confirmado 01:03 UTC del 7 nov (versión `8f3cdc322808`) y después **Desplegar Juan 9** (`cb541f8`): Juan
  va después de Odoo porque llama a `guardar_correo` y `no_quiere_novedades`, que un Odoo viejo no tiene. El CI #289
  (sin los arreglos de la segunda revisión) se canceló para relanzarlo completo (CI #290): una sola subida.

### 2026-11-06 (8): «Ver más» en la foto del catálogo y Dependabot, en producción

- Pedido de la dueña: en «Foto del catálogo» había 38 bibliotecas y solo salían 8. Ahora 12 por vuelta y «Ver más»
  trae las siguientes sin repetir (`buscar_catalogo(…, desde=)`, tope 40 por vuelta). Con las actualizaciones de
  Dependabot #7 y #78 a #81 (Juan con el SDK de IA 7 y una prueba que vigila cómo arma la llamada) y la regla de no
  proponer `@types/node` de otra versión mayor.
- **En producción:** PR #88 (`main` = `513b094`, árbol = `3a1c1d3`), **Desplegar 56** sano y confirmado 21:22 UTC
  (versión `3a1c1d3fc144`) y **Desplegar Juan 8** (`513b094`). El **Desplegar 55 falló** por pasar el SHA del *squash*
  como `app_version` (trampa ya escrita; ver CONTEXTO_AGENTICO). Producción nunca dejó de estar sana.
- Un reinicio del contenedor cortó a dos agentes (Camila 1b y Brian) y al vigilante del CI: los *worktrees* guardaron
  todo sin commit y los agentes siguieron donde iban al reanudarlos con un mensaje.
- La dueña aprobó las capturas de Brian («perfecto») y decidió que la casilla de novedades se active sola al agregar
  un correo (la vendedora la desactiva si el cliente dice que no). Las dos cosas siguen en preparación, junto con la
  pantalla de Sofía (después, las tres en producción: Desplegar 57 y 58).

### 2026-11-06 (7): la pantalla de Sofía

- Pedido de la dueña: «Sofía puede mejorar mucho, sobre todo la interfaz visual». **Solo la interfaz**
  (`dcasa_sofia/static/src/`): qué propone, los permisos y lo que hace cada botón no cambiaron. Ver
  [SOFIA.md](SOFIA.md) › «Cómo se ve y se usa».
- Lo que costaba (capturas «antes»): lo urgente era una etiqueta igual a las demás; cada tarjeta traía 3 etiquetas,
  título, porqué, una caja de texto de hasta 12 líneas y un párrafo repetido de «Le pide sus datos»; en el celular la
  cabecera y 4 filas de filtros llenaban media pantalla; «Descartar» junto al botón principal; el filtro de Gerencia
  por vendedora era una lista sin números; al aprobar la tarjeta desaparecía de golpe y todo subía; vacío y carga eran
  un texto gris; desde «Organizar con Sofía» no se veía nada hasta terminar la revisión.
- Ahora: secciones «Hoy sin falta» (azul) / «Hoy» / «Cuando puedas» con su número y un resumen arriba; filtro por tipo
  y (Gerencia) por vendedora con conteos cruzados, al lado en la computadora y en una tira pegada arriba en el celular;
  tarjetas compactas con el mensaje como burbuja y «Editar»; la acción principal grande; «Ver la oportunidad» y
  «Descartar» (sin confirmación, como siempre) abajo y aparte; al aprobar la tarjeta dice lo que pasó en su lugar y del
  mismo alto, y se cierra despacio; «Todo al día» y «Listo por aquí» con «Ver todo»; esqueleto al cargar y, desde el
  CRM, primero lo que ya había y la revisión encima. Baja con la rueda y con el dedo.
- Pruebas: `test_sofia_pantalla.py` (nuevo, 9; la rueda y el dedo por el protocolo de Chrome) y las de navegador
  ajustadas a «Editar»: 70 en verde en base limpia (68 de Sofía y `dcasa_interfaz` › `TestInicioScroll`). Capturas
  `antes_…`/`despues_…` en el scratchpad de la sesión (`capturas_sofia`), con datos de prueba. **Sin push ni
  despliegue**: falta que la dueña vea las capturas. *(Después: le gustaron, «Descartar» queda sin confirmación y está
  en producción con Desplegar 57.)*
- Aprendido: el minificador de Odoo (`rjsmin`) aprieta los espacios de una plantilla `` `…` `` anidada dentro de
  `${…}` («p. m.(la pidió»); hay tres casos viejos en Conversaciones (tarea aparte). Ver CONTEXTO_AGENTICO.

### Entradas anteriores (una línea cada una; el texto completo en [historico/BITACORA_ANTERIOR.md](historico/BITACORA_ANTERIOR.md))

- **2026-11-06 (6):** Brian al día.
- **2026-11-06 (5):** Camila etapa 2 («a lo grande, todo conectado con todo»), en producción.
- **2026-11-06 (4):** Camila, la asistente del mail marketing (módulo nuevo `dcasa_camila`, etapa 1).
- **2026-11-06 (3):** la varita mágica («Sugerir») escribe siempre, o dice por qué y deja reintentar.
- **2026-11-06 (2):** la calculadora de envíos en el menú Envíos (módulo nuevo `dcasa_envios`).
- **2026-11-06 (1):** limpieza y mantenimiento; WhatsApp guarda antes de contestar; Camila (diseño).
- **2026-11-05 (4):** «Guardar y responderle».
- **2026-11-05 (3):** Sofía baja con scroll; «Guarda sus datos».
- **2026-11-05 (2):** Sofía, la asistente del CRM (módulo nuevo `dcasa_sofia`).
- **2026-11-05:** tasa de cierre en el Resumen de Juan; idea del agente del CRM.
- **2026-11-04:** tarifas de envío (propuesta, en pausa) y clientes repetidos (buscar por celular, «Es esta persona»).
- **2026-11-03 (tarde y noche):** tres paneles en el Inicio, CRM al chat, vendedoras activas, notas de voz y fotos.
- **2026-11-02 (tarde) y 2026-11-03 (madrugada):** Juan en el WhatsApp de la tienda, medios en el chat, origen y cotizaciones que vencen.
- **2026-11-02:** Valor del inventario y cobrado por forma de pago.
- **2026-10-27 (tarde):** «Rastrear inventario» bloqueado por la regla del motivo del ajuste; motivo del sistema y
  Desplegar 32 (PR #65).
- **2026-10-26 (noche) y 2026-10-27:** traslado de `dcasapty.com` al Cloudflare de D'CASA (Desplegar 29 a 31, PR #64) y
  correo con Resend (`info@` reenviado al Gmail de la empresa).
- **2026-10-23 (tarde):** lentitud resuelta (el Inicio y el panel de Bodega ya no miran el pago factura por factura),
  reintento del borde ante «Network connection lost», nota de entrega sin repetidos y scroll de Marketing (Desplegar 27,
  PR #62); combos cama + colchón con el descuento en su renglón y los 4 descuentos aprobados (Desplegar 28, PR #63); la
  dueña creó los diarios Visa, Mastercard, American Express, Clave y KrediYa y archivó «Tarjeta» y «Punto de venta BN».
- **2026-10-23 (madrugada):** datos limpios en producción: nombres en formato título para el cliente, productos repetidos,
  costo cerrado, clave de descuento por Telegram y abonos por vencer (Desplegar 26, PR #61). Desplegar 25 no tocó
  producción: Odoo estaba apagado (503; causa sin confirmar).
- **2026-10-22 (noche):** la tanda del 22 oct en producción (Desplegar 24, PR #60): panel de Bodega, Reponer con tiempo de
  llegada, ventas por día, app Marketing, combos, teléfono fijo, mermas y alertas de bodega, adelantos, comprobante de
  planilla y ZIP de comprobantes.
- **2026-10-22:** la dueña personalizó la pantalla de entrada de Cloudflare Access y confirmó que la cámara se ve en su
  iPhone; tanda grande en ocho ramas.
- **2026-10-19:** la cámara del lector se pinta en un lienzo (Desplegar 23, PR #59); las vendedoras cotizan y no facturan
  sueltas, la cámara se ve y Compras › Reponer (Desplegar 22, PR #58); las 14 preguntas que faltaban, para el jefe.
- **2026-10-18:** ticket promedio y unidades por tipo (Desplegar 21, PR #57); Ajustes se guarda, Inicio de Gerencia sobre
  facturas y reglas contables de la gerencia (Desplegar 19, PR #55); `/master` con diagnóstico, «Iniciar sesión» a Mi
  cuenta, documentación para replicar y Meta apagada (Desplegar 20, PR #56); respuestas I1–L8 del jefe.
- **2026-10-17:** barra del celular y menú con esquinas suaves (Desplegar 18, PR #54); abonos, Mi cuenta, celular y correo
  obligatorios, comparador de ventas y correos apagados (Desplegar 17, PR #53); comparación con el mes pasado y cámara del
  Escáner (Desplegar 15); 17 decisiones de la dueña; permisos de vendedoras y Meta en sus ramas.
- **2026-10-16:** incidente 1 (las Etapas 1 y 2 rompieron el Inicio; arreglo: la imagen sabe su commit y la salud es
  estricta, Desplegar 9); versiones estables 1 y 2; Desplegar 10 a 13 (Etapa 3, Inicio con cotizaciones arriba, bono por
  meta, pedidos repetidos, meta de la vendedora); decisiones sobre Juan; regla de revisión adversarial.
