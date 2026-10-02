# Operación del sitio y el ERP de D'CASA

Guía para el dueño, en lenguaje claro. La referencia técnica está en
[DESPLIEGUE.md](DESPLIEGUE.md) y el contrato entre el Worker y el contenedor en
`edge/CONTRATO_CONTENEDOR.md`.

## Cómo funciona, en una frase

Odoo (el sistema) y su base de datos viven juntos en **un contenedor de Cloudflare** que no tiene
disco permanente; por eso **cada cambio en la base se copia a R2** (el almacenamiento de Cloudflare)
casi al instante, y cada vez que el contenedor arranca, **se reconstruye solo desde esa copia**.

## Qué aceptamos perder y cuánto tarda en volver

| | Qué significa | Valor |
|---|---|---|
| **RPO** (pérdida máxima aceptada) | si el contenedor muere de golpe, se pierde lo que se guardó en el último minuto aprox. | **≈ 1 minuto** (decisión del 2026-10-01). Medido en prueba: 8 a 52 s, mediana 33 s |
| **RTO** (tiempo para volver) | desde que cae hasta que el sitio responde otra vez | medido con almacenamiento local: ≈ 46 s. **Con R2 real todavía no se midió**; la meta es < 5 min |

Fuente de las cifras: `docs/auditoria/DECISION_Y_PLAN.md` y `docs/auditoria/BITACORA.md` (r3-datos).
En la práctica: si el sistema se cae en medio de una venta, puede que haya que volver a cargar lo
último que se hizo en ese minuto. Por eso, tras cualquier caída, **revisar la última factura o pedido**.

## Cuánto cuesta

Según `docs/auditoria/ronda3/cf-plataforma.md` (precios oficiales de Cloudflare, 2026-10-01):

| Concepto | Costo al mes |
|---|---|
| Producción: plan Workers Paid ($5) + contenedor `basic` encendido 24/7 | **≈ $12** ($11,93 a $12,78 según cuánto trabaje el procesador) |
| Respaldos y adjuntos en R2 | $0 mientras todo quepa en los 10 GB gratis (hoy la base pesa unos cientos de MB; las fotos y PDF van aparte, en `adjuntos/`, sin copias repetidas en cada respaldo) |
| Staging (entorno de prueba) | solo las horas que está despierto; se duerme solo tras 1 h sin visitas y el cron horario **no** lo despierta (antes lo tenía encendido ~50 % del tiempo: ≈ +$4/mes) |
| Brian (inteligencia artificial) | aparte: lo que consuma el proveedor de IA |

Revisar la factura real el primer mes (panel de Cloudflare → *Billing*) y compararla con esta tabla.
Para que nada crezca sin avisar, ver «Barandas de costo» más abajo (alertas de presupuesto, reglas de
R2, depuración y reporte mensual). Detalle de qué crece y cuándo: `docs/auditoria/ronda4/costos-y-limpieza.md`.

---

## Preparación (una sola vez)

### 1. Plan de Cloudflare

Panel de Cloudflare → *Workers & Pages* → *Plans* → **Workers Paid** ($5/mes). Sin este plan no hay
contenedores.

### 2. Crear los buckets de R2

Un bucket es una «carpeta» de almacenamiento. Se usan dos, uno por entorno, **nunca compartidos**:

1. Panel → **R2 Object Storage** → **Create bucket**.
2. Nombre: `dcasa-respaldos`. En *Location* elegir la pista **Eastern North America (ENAM)**.
   Crear.
3. Repetir con `dcasa-respaldos-staging`.
4. No activar acceso público en ninguno.
5. **No** crear reglas de ciclo de vida (*Object lifecycle rules*) que borren o expiren el prefijo
   `adjuntos/`: ahí están las fotos y PDF del sistema y los borra solo Odoo, con su propio plazo
   (ver «Adjuntos en R2» más abajo). Si alguna vez se agrega una regla, que sea solo para
   `pgbackrest/` o `pg_dump/`.

### 3. Crear los tokens de R2 (las llaves de los buckets)

1. Panel → **R2 Object Storage** → en *Account Details*, **Manage** junto a *API Tokens*.
2. **Create Account API token**.
3. Nombre: `dcasa-respaldos-produccion`. Permiso: **Object Read & Write**. En *Specify bucket(s)*
   elegir **solo** `dcasa-respaldos`.
4. Crear y **copiar en el gestor de contraseñas** el *Access Key ID* y el *Secret Access Key*
   (el segundo se muestra una sola vez).
5. Repetir para staging (`dcasa-respaldos-staging`), con su propio token.

### 4. Crear el token de despliegue (para GitHub)

Panel → *Manage Account* → **Account API Tokens** → *Create Token* → personalizado, con permisos de
**Workers** (administrador, para que pueda crear `dcasa` y `dcasa-staging` la primera vez),
**Containers: Edit** y **Account Settings: Read**. Cuando se active el dominio, agregar
*Zone → Workers Routes → Edit* para `dcasapty.com`. Copiar el token y el **Account ID** (aparece en la
página principal de *Workers & Pages*).

### 5. Generar las claves propias

En una terminal (o pedírselo a quien administre el sistema), una vez por clave y **por entorno**:

```bash
openssl rand -hex 32
```

| Clave | Para qué | ¿Se puede cambiar después? |
|---|---|---|
| `PGBACKREST_CIPHER_PASS` | cifra los respaldos en R2 | **Nunca.** Sin ella, los respaldos no se pueden abrir |
| `DCASA_PIN_PEPPER` | protege el PIN de los socios | **Nunca.** Cambiarla invalida el PIN de todos los socios |
| `RESPALDO_TOKEN` | autoriza pedir un respaldo a mano | sí |
| `TIENDA_FEED_TOKEN` | la tienda rápida (páginas estáticas): Odoo y el Worker se reconocen con ella | sí (se sube en cada despliegue) |
| `ODOO_ADMIN_PASSWORD` | clave del usuario `admin` de Odoo | sí (desde Odoo) |
| `ODOO_MASTER_PASSWORD` | contraseña maestra de Odoo, distinta de la anterior | sí |

**Las dos primeras se guardan en el gestor de contraseñas antes de cualquier despliegue.** Cloudflare
no deja volver a leerlas: esa copia es la única.

### 6. Cargar todo en GitHub

GitHub → repositorio → *Settings* → **Environments**:

1. Crear `staging` y `production`.
2. En `production`: activar **Required reviewers** y ponerse como revisor; en *Deployment branches*
   permitir solo `main`. Así **nada llega a producción sin tu aprobación**.
3. En cada uno, cargar los secretos y variables de la tabla de [DESPLIEGUE.md §3](DESPLIEGUE.md)
   (los de staging con las llaves de staging).

Si falta algo o quedó un valor de ejemplo (`CAMBIAR`, `<...>`), el despliegue se detiene antes de
tocar nada y dice qué falta.

---

## Primer despliegue a staging

1. GitHub → **Actions** → **CI/CD** → **Run workflow**.
2. Rama `main`, *desplegar_en* = `staging` → **Run workflow**.
3. Esperar a que todo quede en verde (tests ≈ 15-25 min, despliegue unos minutos más). El paso
   «Esperar a que el sitio esté sano» confirma que respondió.
4. Abrir `URL_SITIO` de staging y luego `/web/login` → usuario `admin`, clave `ODOO_ADMIN_PASSWORD`
   de staging.
5. Comprobar: portada, `/shop`, `/socios`, entrar al backend.

Staging se duerme tras 1 hora sin visitas; la siguiente visita lo despierta (muestra «estamos
arrancando» unos segundos) y **restaura la base desde R2**: cada despertar es un pequeño simulacro.
Mientras duerme **no corre nada**: ni el cron horario del Worker lo despierta ni se hace el respaldo
diario (no hay cambios que respaldar). Producción, en cambio, sigue encendida 24/7.

## Desplegar a producción

Cada vez que se aprueba y une un cambio a `main`, GitHub prueba todo y **espera tu aprobación**:
Actions → la ejecución → **Review deployments** → *Approve*. Antes de desplegar hace un respaldo de la
base; si el respaldo falla, no despliega.

- Desplegar **fuera del horario de venta**: durante el cambio el sitio muestra «estamos arrancando»
  uno o dos minutos. Las sesiones se guardan en la base, así que al volver nadie tiene que iniciar
  sesión de nuevo ni pierde su carrito.
- Si el cambio toca módulos de Odoo de forma importante, **probar primero en staging**.

## Simulacro mensual de restauración

Cada PR y cada cambio a `main` ya corre un simulacro automático (con un almacenamiento de prueba). Una
vez al mes conviene hacer uno **con R2 de verdad**, en staging:

1. Entrar al backend de staging y crear algo reconocible: p. ej. un contacto «Simulacro AAAA-MM-DD
   HH:MM» con la hora exacta.
2. Esperar **2 minutos** (más que el RPO).
3. Forzar un reinicio: Actions → **CI/CD** → *Run workflow* con `desplegar_en = staging`, o dejarlo
   dormir (1 h sin visitas).
4. Abrir staging, anotar **cuánto tardó en volver** (RTO) y comprobar que el contacto está.
5. Anotar fecha, RTO y resultado en `docs/auditoria/BITACORA.md`.

Si el contacto no aparece, o tarda más de 5 minutos, **no seguir cargando datos reales** y avisar a
quien mantiene el sistema: es la regla de salida de la Fase 1.

## Si el sitio se cae

1. Abrir `https://dcasapty.com/__edge/health` (o la de staging). Responde un JSON:
   - `"odoo": "arrancando"` → está restaurando o arrancando: esperar 3 minutos y recargar.
   - `"odoo": "sin_configurar"` (con `faltan`) → falta un secreto en Cloudflare: revisar el
     environment de GitHub y volver a desplegar.
   - `"odoo": "detenido"` o `"error"` → ver los logs (abajo). El sistema intenta rearrancar solo a los
     30 s (como mucho una vez cada 10 min) y además cada hora (solo producción; staging espera a la
     próxima visita).
2. ¿Se cayó justo después de un despliegue? → **Volver atrás un despliegue** (abajo).
3. ¿Sigue caído y no hubo despliegue? → revisar en los logs si falla la restauración desde R2
   (`arranque_fallido`) y avisar a quien mantiene el sistema. **No borrar nada en R2.**
4. Después de volver: revisar la **última factura y el último pedido** (pueden faltar los segundos
   previos a la caída).

## Volver atrás un despliegue

Se hace en dos pasos, siempre en este orden:

1. **Restaurar la base al momento anterior al despliegue.** El resumen del despliegue malo (Actions →
   la ejecución → *Summary*) dice la hora del «Respaldo previo». Para arrancar restaurando a esa hora,
   ver «Restaurar a un punto en el tiempo».
2. **Desplegar la versión anterior:** abrir el resumen del último despliegue **bueno** y copiar
   `app_version` e `imagen_digest`. Actions → **Desplegar** → *Run workflow* → entorno, esos dos
   valores, y desmarcar *respaldo_previo* si el sitio está caído. No se reconstruye nada: se usa la
   misma imagen que ya funcionó.

**Nunca** hacer solo el paso 2: la versión vieja de Odoo sobre una base ya actualizada puede romper
datos.

## Restaurar a un punto en el tiempo

Sirve para «volver a las 10:42 de hoy», p. ej. si se borró algo por error o un despliegue dañó datos.
R2 guarda el respaldo diario y todos los cambios (WAL), así que se puede volver a **cualquier momento**
cubierto por los respaldos.

- **Mirar sin tocar producción** (recomendado primero): restaurar una copia en otra máquina o en
  staging a esa hora, buscar el dato y volver a cargarlo a mano en producción. Así no se pierde lo
  que se hizo después.
- **Volver producción entera a esa hora**: se pierde todo lo posterior. Solo con decisión del dueño.

**Cómo se pide:** poner en el Worker la variable `DCASA_RESTAURAR_HASTA` con la hora **y la zona
horaria** (obligatoria), p. ej. `DCASA_RESTAURAR_HASTA="2026-10-01 10:42:00-05"` (hora de Panamá), y
reiniciar el contenedor (desplegar de nuevo). Al arrancar restaura con pgBackRest `--type=time` hasta
esa hora y promueve la base. Se aplica **una sola vez**: queda una marca en R2 (`dcasa-control/`) y un
reinicio posterior con la variable aún puesta no vuelve a restaurar. Después de comprobar que todo
está bien, quitar la variable. Ensayado en el simulacro (`scripts/simulacro_restauracion.sh`).

Los archivos (fotos, PDF) no viajan con la base: siguen en `adjuntos/` del bucket y la base
restaurada los encuentra ahí, porque nada que use una base de los últimos 45 días se borra de R2
(ver «Adjuntos en R2»).

## Adjuntos en R2 (fotos, PDF y archivos del sistema)

**Qué es.** Los archivos que se suben a Odoo (fotos de productos, PDF de facturas, adjuntos de
correos, los archivos de estilo del sitio) ya no se guardan dentro de la base: van a R2, al mismo
bucket de los respaldos, en la carpeta `adjuntos/`. La base solo guarda dónde está cada uno
(`r2://adjuntos/ab/abcd…`, el nombre es la huella sha1 del contenido: dos archivos iguales se
guardan una sola vez). Así la base pesa mucho menos, los respaldos son más rápidos y restaurar
tarda menos. Lo hace el módulo `dcasa_adjuntos_r2`.

**Cómo se activa.** Solo: al arrancar, el contenedor fija `ir_attachment.location = r2` si tiene
las credenciales de R2 (siempre en producción y staging) y `db` si no (CI, desarrollo). Los archivos
que ya estaban en la base los sube un cron cada 30 min, por lotes («Adjuntos en R2: mover según
ir_attachment.location»).

**Si R2 falla.** Al subir un archivo, el error se muestra y **no se guarda nada** (se puede
reintentar). Al leer, la página de la foto da error en vez de mostrar un archivo vacío. En los logs
del contenedor aparecen como `Adjuntos en R2: …`.

**Por qué nunca se borra en R2 al borrar en Odoo.** La base se puede restaurar a un momento
anterior (pgBackRest guarda 7 días; los volcados diarios, 30). Esa base vieja apunta a los archivos
que tenía entonces: si se hubieran borrado de R2 al borrarlos en Odoo, la restauración quedaría con
fotos y PDF rotos. Por eso los borra un cron diario («Adjuntos en R2: recolectar objetos sin uso»)
y solo si se cumplen las tres cosas:

1. ninguna fila de la base actual lo usa;
2. el cron lo viene viendo sin uso desde hace más de **45 días** (más que los 30 de los volcados);
3. nadie lo volvió a subir en esos 45 días (cada vez que se guarda el mismo contenido se sube de
   nuevo y su fecha en R2 se renueva).

El plazo se cambia con el parámetro de sistema `dcasa_adjuntos_r2.dias_retencion` (mínimo 31). Si
algún día se alarga la retención de los respaldos (`RESPALDO_DUMP_DIAS`), **subir este plazo
primero**. Si el cron estuvo parado más de 3 días, la cuenta empieza de cero (no borra a ciegas).

**Restaurar implica las dos cosas.** Una restauración necesita el respaldo de PostgreSQL **y** la
carpeta `adjuntos/` del bucket. Restaurar en el mismo bucket (lo normal) no requiere nada más. Para
restaurar en **otro** bucket o cuenta, copiar también `adjuntos/` completo. Nunca vaciar ni expirar
`adjuntos/` (ver «Crear los buckets»). Una base restaurada que no encuentra un archivo lo deja en
el log como `Adjuntos en R2: falta el objeto …` y lo muestra vacío.

**Emergencia: traer todo de vuelta a la base** (p. ej. para dejar de depender de R2). En el Worker,
variable `DCASA_ADJUNTOS=db` y desplegar de nuevo. Desde ese arranque los archivos nuevos van a la
base y el mismo cron de cada 30 min trae, por lotes, los que están en R2 (mientras tanto se siguen
leyendo de R2, así que no hay que esperar a que termine). Si un archivo no se puede leer de R2, no se
toca (nunca se escribe vacío encima) y queda en el log. Para volver a R2: quitar la variable y
desplegar. Los objetos de R2 no se borran con esto: los recogerá el cron pasados los 45 días. La base
crece de nuevo (hoy ~120 MB de adjuntos); revisar que quepa en el disco del contenedor.

**Seguridad.** Odoo usa la misma llave de R2 que los respaldos (el bucket es uno por entorno y un
token de R2 no se puede limitar a una carpeta). No es una frontera nueva: Odoo y PostgreSQL ya
corren con el mismo usuario dentro del contenedor. La clave de cifrado de los respaldos
(`PGBACKREST_CIPHER_PASS`) nunca llega a Odoo.

## Barandas de costo (hacer una vez, en el panel de Cloudflare)

Nada de esto se configura desde el código: lo hace el dueño en el panel, una sola vez.

### Alertas de presupuesto ($10 y $20)

Avisan por correo cuando el gasto **por uso** proyectado del mes (aparte de los $5 fijos del plan)
pasa de un monto. **No cortan el servicio**, solo avisan; se calculan una vez al día.

1. Panel de Cloudflare → **Manage Account** → **Billing** → **Billable Usage**.
2. **Set Budget Alert** → monto `10` → **Create**.
3. Repetir con `20`.
4. (Otra vía: **Notifications** → **Add** → **Budget Alert**.)

Ruta verificada en la documentación oficial (changelog «Billable Usage dashboard and Budget alerts»,
2026-04-13). Desde 2026-06-15 Cloudflare crea una de $10 por defecto: si ya existe, crear solo la de $20.
En la misma página **Billable Usage** se ve el gasto día a día por producto.

### Reglas de ciclo de vida de R2

Red de seguridad por si la poda del script falla, y la copia anual a almacenamiento barato. En el
bucket `dcasa-respaldos` (y, con 7 días en `pg_dump/`, en `dcasa-respaldos-staging`):

| Regla | Prefijo | Acción |
|---|---|---|
| `volcados-35-dias` | `pg_dump/` | borrar a los **35 días** (el script ya poda a los 30) |
| `anual-ia` | `anual/` | pasar a **Infrequent Access** a los **30 días** (nunca borrar) |
| `multipart-1-dia` | *(todo el bucket)* | abortar subidas por partes incompletas a **1 día** |

**No** poner ninguna regla sobre `pgbackrest/` ni sobre `adjuntos/` (fotos y PDF de Odoo: los borra solo el cron de «Adjuntos en R2», a los 45 días sin uso). pgBackRest borra lo suyo, y borrar por fuera rompe la
cadena de respaldos.

Desde una terminal con `wrangler` (comandos verificados en la documentación de Wrangler):

```bash
cd edge
npx wrangler r2 bucket lifecycle add dcasa-respaldos volcados-35-dias pg_dump/ --expire-days 35
npx wrangler r2 bucket lifecycle add dcasa-respaldos anual-ia anual/ --ia-transition-days 30
npx wrangler r2 bucket lifecycle add dcasa-respaldos multipart-1-dia --abort-multipart-days 1
npx wrangler r2 bucket lifecycle add dcasa-respaldos-staging volcados-7-dias pg_dump/ --expire-days 7
npx wrangler r2 bucket lifecycle list dcasa-respaldos     # comprobar
```

Desde el panel: **R2 Object Storage** → el bucket → **Settings** → *Object lifecycle rules* → **Add
rule** (nombre, prefijo y acción como en la tabla). *Ruta del panel NO VERIFICADA en la documentación;
los comandos de arriba sí.*

### Copia anual de cierre

El **primer volcado diario de cada año** (el de la madrugada del 1 de enero = la base al cierre del año
anterior) se copia solo a `anual/dcasa-AAAAMMDDTHHMMSSZ.dump.enc` y **no se borra nunca** (la poda de 30
días solo mira `pg_dump/`). Ocupa ~1 volcado por año; con la regla `anual-ia` cuesta centavos. El año
en que se estrena el sistema, la copia anual es el primer volcado que se haga. Plazo legal de
conservación en Panamá: **confirmarlo con el contador** (se cita 5 años, NO VERIFICADO). Para
restaurarla: igual que un volcado diario (`openssl … | pg_restore`, ver `docker/pg.sh`). Se listan con
`dcasa-respaldo info`.

El volcado diario ya no se escribe entero en el disco del contenedor: sube a R2 por partes de 64 MB
(`RESPALDO_DUMP_PARTE_MB`), así el disco de 4 GB alcanza para una base más grande.

### Depuración y reporte mensual (automáticos, día 1 de cada mes)

Dos acciones planificadas de Odoo (Ajustes → Técnico → Acciones planificadas, «D'CASA: …»):

- **Depuración** (03:30 Panamá): borra archivos adjuntos huérfanos (de registros que ya no existen, con
  más de 7 días) y correos que fallaron hace más de 90 días. **Nunca** toca facturas, contabilidad, el
  libro de Socios ni el registro de Brian, ni archivos que algo todavía usa. Deja una línea
  `DCASA_LIMPIEZA adjuntos_huerfanos=… bytes_liberados=… correos_fallidos=…`.
- **Reporte de tamaños** (03:45 Panamá): tamaño de la base, las 10 tablas más grandes, bytes de
  adjuntos por tipo de registro y memoria real del contenedor, en una línea `DCASA_METRICA {…}`.
  Si la base pasa de **0,7 GB** (o hubo un corte por falta de memoria) deja `DCASA_ALERTA`: es la señal
  para sacar los archivos a R2 o subir el contenedor de tamaño **antes** de llegar a ~1 GB.

Las dos quedan también en Odoo: Ajustes → Técnico → **Registros** (`dcasa.limpieza`,
`dcasa.reporte_tamanos`). Umbrales (Ajustes → Técnico → Parámetros del sistema):
`dcasa.limpieza.adjuntos_dias` (7), `dcasa.limpieza.correos_fallidos_dias` (90),
`dcasa.limpieza.modelos_protegidos` (vacío: modelos extra que no se tocan, separados por coma),
`dcasa.reporte.alerta_gb` (0.7). Lo que Odoo ya limpia solo (visitantes del sitio a los 60 días,
sesiones a los 7, notificaciones, bus) no se repite.

## Tienda rápida (páginas estáticas del Worker)

La portada, el catálogo (`/shop`, categorías y páginas), las fichas, Visítanos, Privacidad y Términos
se pueden servir **desde el borde de Cloudflare** en vez de pedírselas a Odoo cada vez: cargan en
1-2 s en un celular y no gastan la CPU del contenedor. Las URL son **las mismas** de Odoo. El carrito,
el pago, `/my` (portal del cliente), `/socios`, el panel y todo lo demás siguen en Odoo.

**Cómo se mantiene al día.** Cada cambio que se ve en el sitio (precio, nombre, publicar/despublicar,
fotos, categorías, existencias, una venta confirmada o cancelada, una factura publicada) deja una
marca en Odoo; a los ~20 segundos Odoo avisa al Worker y el Worker regenera las páginas que cambiaron
(normalmente en menos de un minuto; Cloudflare tarda hasta ~60 s más en propagarlas). Además, cada
hora el Worker revisa todo por si un aviso se perdió.

**Encenderla:**

1. Cargar el secreto `TIENDA_FEED_TOKEN` (§5: `openssl rand -hex 32`, uno distinto por entorno) en
   GitHub → Environments → `staging` (y luego `production`).
2. El token de despliegue de Cloudflare necesita además el permiso **Workers KV Storage: Edit**
   (el primer despliegue crea solo el almacén «TIENDA» de cada entorno).
3. Desplegar. Staging ya viene con `TIENDA_ESTATICA = "on"`: revisar `https://<staging>/`, `/shop` y una
   ficha (la cabecera `X-Dcasa-Tienda: estatica` confirma que salió del borde). Staging nunca se
   indexa en Google (`X-Robots-Tag: noindex` en todas sus respuestas).
4. Si Odoo todavía no avisó nada, forzar la primera generación:
   `curl -X POST -H "Authorization: Bearer <TIENDA_FEED_TOKEN>" https://<sitio>/__edge/tienda/regenerar`
   (responde con cuántas páginas escribió).
5. Para producción: cambiar `TIENDA_ESTATICA` a `"on"` en `edge/wrangler.jsonc` (raíz) y desplegar.
   Para apagarla: `"off"` y desplegar; todo vuelve a salir de Odoo al instante.

**Si algo se ve viejo:** repetir el paso 4. Si el Worker no puede leer una página, la pide a Odoo
(nunca una página en blanco). Logs: eventos `tienda_regenerada` y `tienda_lectura_fallida`.

## Dónde ver los logs

| Qué | Dónde |
|---|---|
| Lo que pasa en el sitio (arranques, caídas, respaldos) | Panel de Cloudflare → *Workers & Pages* → `dcasa` (o `dcasa-staging`) → **Logs**. Buscar eventos `arranque_listo`, `arranque_fallido`, `contenedor_detenido`, `respaldo` |
| El contenedor (Odoo y PostgreSQL por dentro) | Panel → *Workers & Pages* → **Containers** → `dcasa-odoocontainer` → instancias y logs. Para no gastar eventos de log, Odoo no escribe una línea por visita (`werkzeug:WARNING`; los errores sí salen) y PostgreSQL no anota los *checkpoints*. Para depurar: variable `ODOO_LOG_HANDLER=werkzeug:INFO` |
| Memoria real del contenedor | Buscar `"evento": "memoria"` en los logs del contenedor: una línea ~3 min después de cada arranque (`momento: arranque`) y otra cada vez que Odoo se cae (`odoo_caido`). `cgroup.anon` = memoria que de verdad usan los procesos; `cgroup.file` = caché de disco (el kernel la libera sola; el gráfico del panel puede incluirla); `procesos.odoo` / `procesos.postgres` = RSS y PSS (la PSS de PostgreSQL es la buena: la RSS cuenta `shared_buffers` en cada proceso); `cgroup.eventos.oom_kill` > 0 = el kernel mató un proceso por falta de memoria. También va dentro del reporte mensual (`DCASA_METRICA`) |
| Depuración y tamaños del mes | Logs del contenedor: `DCASA_LIMPIEZA`, `DCASA_METRICA`, `DCASA_ALERTA`; o en Odoo: Ajustes → Técnico → **Registros** |
| En vivo desde una terminal | `cd edge && npx wrangler tail --env=""` (staging: `--env=staging`) |
| Despliegues y pruebas | GitHub → **Actions** → la ejecución → cada paso; el *Summary* trae la versión desplegada y el respaldo previo |

## Calendario

| Cada… | Qué |
|---|---|
| lunes | revisar los PR de Dependabot (actualizaciones): si el CI está en verde, aprobar. Los que suban PostgreSQL de versión mayor se cierran |
| despliegue | aprobarlo fuera del horario de venta y mirar el sitio al terminar |
| mes | simulacro de restauración en staging; revisar la factura de Cloudflare (*Billable Usage*) y el reporte `DCASA_METRICA` del día 1 (¿la base se acerca a 0,7 GB?) |
| enero | comprobar con `dcasa-respaldo info` que existe la copia anual del año que cerró |
| siempre | las claves `PGBACKREST_CIPHER_PASS` y `DCASA_PIN_PEPPER` guardadas en el gestor de contraseñas, nunca cambiadas |
