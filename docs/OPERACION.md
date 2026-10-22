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
5. **No** crear reglas de ciclo de vida (*Object lifecycle rules*) que borren o expiren los prefijos
   `adjuntos/` ni `fuentes/` (originales de fotos, ver «Cómo subir fotos»). En `adjuntos/` están las
   fotos y PDF del sistema y los borra solo Odoo, con su propio plazo (ver «Adjuntos en R2» más abajo). Si alguna vez se agrega una regla, que sea solo para
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
| `TIENDA_FEED_TOKEN` | la tienda rápida (caché de páginas en el borde): Odoo y el Worker se reconocen con ella | sí (se sube en cada despliegue) |
| `ODOO_ADMIN_PASSWORD` | clave del usuario `admin` de Odoo | sí (desde Odoo) |
| `ODOO_MASTER_PASSWORD` | contraseña maestra de Odoo, distinta de la anterior | sí |

**Las dos primeras se guardan en el gestor de contraseñas antes de cualquier despliegue.** Cloudflare
no deja volver a leerlas: esa copia es la única.

### 6. Cargar todo en GitHub

GitHub → repositorio → *Settings* → **Environments**:

1. Crear `staging` y `production`.
2. En `production`: en *Deployment branches and tags* elegir *Selected branches* y permitir solo `main`.
   («Required reviewers» no existe en este repositorio privado.) **Nada llega a producción sin que tú lo lances**:
   un merge a `main` solo corre pruebas, y a producción se sale con *Run workflow* y `desplegar_en = produccion`.
3. En cada uno, cargar los secretos y variables de la tabla de [DESPLIEGUE.md §3](DESPLIEGUE.md)
   (los de staging con las llaves de staging).

Si falta algo o quedó un valor de ejemplo (`CAMBIAR`, `<...>`), el despliegue se detiene antes de
tocar nada y dice qué falta.

---

## Primer despliegue a staging

1. GitHub → **Actions** → **CI/CD** → **Run workflow**.
2. Rama `main`, *desplegar_en* = `staging` → **Run workflow**.
3. Esperar a que todo quede en verde (tests ≈ 15-25 min, despliegue unos minutos más). El paso
   «Esperar a que el sitio esté sano» confirma que respondió. (Mientras espera visita `/web/login` en cada vuelta: la portada
   sale de la copia guardada en el borde y **no** despierta a Odoo; así falló el despliegue 95, con el contenedor en
   `stopped` durante los 20 minutos.)
4. Abrir `URL_SITIO` de staging y luego `/web/login` → usuario `admin`, clave `ODOO_ADMIN_PASSWORD`
   de staging.
5. Comprobar: portada, `/shop`, `/socios`, entrar al backend.

Staging se duerme tras 1 hora sin visitas; la siguiente visita lo despierta (muestra «estamos
arrancando» unos segundos) y **restaura la base desde R2**: cada despertar es un pequeño simulacro.
Mientras duerme **no corre nada**: ni el cron horario del Worker lo despierta ni se hace el respaldo
diario (no hay cambios que respaldar). Producción, en cambio, sigue encendida 24/7.

## Desplegar a producción

**Un cambio unido a `main` NO se despliega solo**: GitHub solo corre las pruebas. A producción se sale cuando
tú lo lanzas: *Actions → CI/CD → Run workflow*, rama **`main`**, `desplegar_en` = **`produccion`**. Se vuelven a
correr todas las pruebas y, si pasan, se despliega. Antes de desplegar hace un respaldo de la base; si el respaldo
falla, no despliega. (Desde otra rama que no sea `main` falla con un aviso: es a propósito.)

- Desplegar **fuera del horario de venta**: durante el cambio el sitio muestra «estamos arrancando»
  uno o dos minutos. Las sesiones se guardan en la base, así que al volver nadie tiene que iniciar
  sesión de nuevo ni pierde su carrito.
- Si el cambio toca módulos de Odoo de forma importante, **probar primero en staging**.

### Si GitHub dice «Artifact storage quota has been hit» (espacio lleno)

Cada despliegue guarda en GitHub una copia temporal de la imagen (~420 MB, archivos `imagen-odoo-…`) que dura 1 día. Si
hubo muchos despliegues seguidos, el espacio de GitHub se llena y el siguiente despliegue falla al subir la imagen. No
es un error del sistema ni se pierde nada: **no toca R2, ni la base, ni las fotos, ni el repositorio**.

1. *Actions → **Limpiar copias temporales** → Run workflow* con `borrar = false` (ensayo): el resumen de la ejecución
   lista qué borraría, con nombre y tamaño. No borra nada.
2. Si la lista es la esperada, lanzarlo de nuevo con `borrar = true`. Solo borra copias `imagen-odoo-…` de más de 24 horas.
3. **Esperar 6 a 12 horas**: GitHub recalcula el espacio ocupado con ese retraso. Después se vuelve a lanzar el despliegue.

Los registros de diagnóstico (simulacro, log de pruebas) ya no ponen la ejecución en rojo si no caben.

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

Es **una sola operación** (restaurar la base y desplegar la versión anterior en el mismo arranque):

1. **Preparar la restauración:** en el Worker, la variable `DCASA_RESTAURAR_HASTA` con la hora del «Respaldo
   previo» del despliegue malo (Actions → la ejecución → *Summary*); ver «Restaurar a un punto en el tiempo».
   **No reiniciar todavía.**
2. **Desplegar la versión anterior:** abrir el resumen del último despliegue **bueno** y copiar
   `app_version` e `imagen_digest`. Actions → **Desplegar** → *Run workflow* → entorno, esos dos
   valores, y desmarcar *respaldo_previo* si el sitio está caído. No se reconstruye nada: se usa la
   misma imagen que ya funcionó. Ese arranque restaura la base y la encuentra como la dejó esa imagen.

**Por qué juntos (#97, 2026-10-16):** si la base se restaura con la imagen nueva todavía puesta, esa imagen la
vuelve a actualizar al arrancar; y una imagen **más vieja** que la que actualizó la base se niega a «bajarla»
(con el código viejo, `odoo -u` borraría columnas y tablas nuevas con sus datos): el sitio no queda sano y el
log dice «NO la actualizo hacia atrás». **Nunca** desplegar la versión vieja sin restaurar.

**Salidas de emergencia** (se pegan en el panel de Cloudflare del Worker solo mientras hagan falta, y se
quitan después):

- `DCASA_PERMITIR_BAJAR=<commit de 40 caracteres de la imagen vieja>`: deja que esa imagen actualice la base
  hacia atrás a sabiendas (se pierden las columnas y tablas que solo tiene la versión nueva). Solo con
  decisión de quien mantiene el sistema.
- `DCASA_HUMO=0`: apaga la prueba de humo del arranque si diera un problema falso. El despliegue igual exige
  la versión nueva con la base al día.

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

## Cómo subir fotos (y Excel de pedidos)

1. **Una foto, un producto**: en Odoo, abrir la ficha del producto y **tocar su foto**: se abre en grande y ahí se
   reemplaza (archivo o cámara del celular), se recorta, se gira o se pone otra como principal. Para subir **varias a
   la vez** y ordenarlas: «Todas» en esa misma ventana, el botón «Fotos del producto» de la pestaña Ventas o
   *Marketing › Fotos* (buscar el producto por nombre, código o código de barras). Se guardan solas en R2
   (`adjuntos/`) y salen en la web al momento. Es el camino normal del día a día (`docs/MARKETING.md`).
2. **Un pedido nuevo del proveedor**: mandarle a Brian (Telegram) el Excel del proveedor con el
   **código** de cada producto; él arma la vista previa, gerencia confirma y los productos nacen sin
   publicar, para publicarlos con Brian uno a uno (`docs/CATALOGO.md` › «Inventario nuevo…»).
3. **Cargas grandes** (muchas fotos de una vez, un Excel completo): en GitHub, carpeta `up media`
   → *Add file* → *Upload files* → *Commit changes*. GitHub las procesa solo (unos 15 minutos) y
   deja el resultado en `up media/RESUMEN.md`. Nombre de cada foto = **código** del producto
   (`CODIGO.jpg`, `CODIGO_2.jpg`…); para un pedido nuevo, el código al inicio del nombre.

### Cómo leer `up media/RESUMEN.md`

Se reescribe con cada subida (lo corre `.github/workflows/up-media.yml`). Tiene cuatro partes:

- **Excel cargados**: qué Excel entró y a dónde se guardó (`fuentes/<pedido>/`).
- **Fotos cargadas: a qué producto fue cada una**: una fila por foto con el producto, *cómo* se
  asignó (por código, por descripción, o decisión revisada a mano) y dónde quedó el original.
- **Lo que no se asignó y por qué**: lo **pendiente** sigue en `up media/` con su motivo (foto dudosa
  entre dos productos, Excel que el programador aún no registró, PDF u otro tipo de archivo);
  lo **conservado** son archivos de la dueña que no son fotos de producto pero sirven (las gráficas de
  Black Weekend → `fuentes/graficas-black-weekend/`); lo **descartado** fue a `descartado/<fecha>/`
  con el motivo en su `LEEME.md`. **Nada se borra**: si algo era de un producto, se vuelve a subir
  con el código en el nombre.
- **Cómo subir más**: las tres reglas de arriba.

Las dudas del catálogo mismo (precios repetidos, medidas, fotos del Excel) están en
`docs/CATALOGO_REVISAR.md`. Si la ejecución falla (Actions → *up media* en rojo), la bandeja queda
tal cual se subió, no se publica nada y hay que avisar a quien mantiene el sistema: el RESUMEN que se
habría escrito queda en el resumen de la ejecución.

### Qué pasa por detrás (para quien mantiene el sistema)

- `scripts/procesar_up_media.py` corre `scripts/importar_catalogo.py` (regenera `catalogo.json`, las
  fotos optimizadas y `docs/CATALOGO_REVISAR.md`), mueve con `git mv` lo procesado y escribe el
  RESUMEN y un `LEEME.md` histórico por carpeta destino. `--simular` imprime el RESUMEN sin mover nada.
- El workflow prueba el resultado (tests del procesador: `python -m unittest discover -s scripts/tests`;
  `scripts/test.sh dcasa_catalogo` instala el módulo con el catálogo nuevo) y **solo si pasa** hace el
  commit con `GITHUB_TOKEN` y lo empuja a `main`; después construye la imagen de ese commit y la
  despliega a **staging** con `desplegar.yml`. A producción se llega como siempre: CI/CD con aprobación.
- Sin bucles: un push con `GITHUB_TOKEN` no dispara workflows, y el commit del bot lleva
  `[skip up-media] [skip ci]`. Si `main` tuviera protección de rama que `GITHUB_TOKEN` no pueda
  saltar, hace falta un PAT fino (*Contents: read and write* en este repositorio, con bypass) en el
  secreto `UP_MEDIA_TOKEN`.
- Una subida detrás de otra: las ejecuciones van en fila (`concurrency: up-media`) y cada una parte de
  la punta de `main`, así no se pisan.
- `up media/inventario-anterior/` es otra carga (capturas del sistema anterior) y el procesador no la
  toca: las subcarpetas de la bandeja quedan «pendientes, de otro flujo».

### Originales pesados: a R2 con `scripts/archivar_fuentes.sh`

Los originales ya procesados viven en `fuentes/<pedido>/` (hoy ≈ 1 GB; la web usa las copias
optimizadas de `addons/dcasa_catalogo/static/img/productos/`, y ni `up media/`, ni `fuentes/`, ni
`descartado/` entran a la imagen Docker). Cuando el repositorio pese demasiado:

1. `scripts/archivar_fuentes.sh listar [--minimo-mb 2]`: qué imágenes de `fuentes/` irían (sin red).
2. `scripts/archivar_fuentes.sh subir`: las sube al bucket de producción (`R2_BUCKET`, las mismas
   cuatro variables `R2_*` de los respaldos) con la **misma ruta** como clave (`fuentes/LTSC-07/…`),
   verifica el tamaño y las anota en `fuentes/ARCHIVADO.tsv` (ruta, sha256, bytes, fecha).
3. `scripts/archivar_fuentes.sh podar`: `git rm` de lo que ya está verificado en R2 y una nota en el
   `LEEME.md` de cada carpeta. Revisar y hacer commit.
4. Para volver a leerlos (regenerar una foto): `scripts/archivar_fuentes.sh traer` (verifica sha256).
   El importador los sigue contando como fuente por el índice y avisa si tiene que leerlos.

`--simular` muestra el plan sin tocar nada. **Nunca borra en R2**; el prefijo `fuentes/` no lleva
reglas de ciclo de vida (como `adjuntos/`). Solo imágenes: los Excel y los LEEME se quedan en el
repositorio. Lo que ya está en la historia de git no se achica con esto: la política vale para lo que
entra desde ahora. Todavía no se ha ejecutado contra R2.

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

### Alertas por Telegram (disco, memoria, base y caídas del contenedor)

Todas llegan por **el mismo bot de Brian** (`TELEGRAM_BOT_TOKEN`), al chat de la dueña y de los demás
administradores que lo tengan vinculado (Brian → Telegram → vincular; es el mismo canal del aviso de
inicios de sesión de administrador). Nada nuevo que crear.

| Aviso | Quién lo manda | Cuándo (por defecto) | Variable que lo ajusta |
|---|---|---|---|
| Disco del contenedor lleno | Odoo, acción planificada «D'CASA: vigilancia de disco, memoria y tamaño de la base» (cada hora) | uso ≥ **80 %** del disco donde viven PostgreSQL y los archivos de Odoo | `DCASA_ALERTA_DISCO_PCT` (parámetro `dcasa.alerta.disco_pct`) |
| Memoria cerca del límite | ídem | memoria **en uso real** (sin contar la caché de disco, que el kernel libera sola) ≥ **90 %** del límite del contenedor | `DCASA_ALERTA_MEMORIA_PCT` (`dcasa.alerta.memoria_pct`) |
| La base pesa demasiado | ídem (y el reporte mensual del día 1) | base > **0,7 GB** | `DCASA_ALERTA_BASE_GB` (`dcasa.reporte.alerta_gb`) |
| El kernel mató un proceso por falta de memoria | ídem | cada vez que `oom_kill` sube desde la revisión anterior | — |
| El contenedor se cayó | El Worker (`contenedor_detenido` con código ≠ 0), porque en ese momento Odoo no está para avisar | cualquier parada con código distinto de 0 (una parada limpia por despliegue no avisa) | `DCASA_ALERTA_TELEGRAM_CHAT`: el **chat_id** de la dueña (lo muestra Brian al vincular). Sin él, queda solo en los logs del Worker |
| El contenedor no arrancó | El Worker (`arranque_fallido`: no abrió el puerto en 7 min) | cada arranque fallido | ídem |

Reglas para no inundar el chat: Odoo no repite **el mismo** aviso antes de **24 h**
(`DCASA_ALERTA_SILENCIO_H`, parámetro `dcasa.alerta.silencio_h`; en el log y en Ajustes → Técnico →
Registros queda cada vez), y el Worker manda como mucho un aviso cada 10 min. `DCASA_ALERTA_TELEGRAM=0`
apaga los avisos de Odoo (siguen saliendo en el log como `DCASA_ALERTA`). Los umbrales se pueden
cambiar también en Ajustes → Técnico → Parámetros del sistema, sin desplegar.

Qué hacer al recibir uno: disco o base → sacar adjuntos a R2 (`DCASA_ADJUNTOS=r2`, ya es lo normal) y
revisar «Depuración y reporte mensual»; memoria u `oom_kill` → mirar `"evento": "memoria"` en los logs del
contenedor y, si se repite, subir el tipo de instancia (`edge/wrangler.jsonc`); caída → «Si el sitio se
cae» y revisar la última factura o pedido.

### Acciones planificadas de Odoo que se apagan o espacian

Odoo trae acciones planificadas (Ajustes → Técnico → Acciones planificadas) para funciones que D'CASA
no usa. En cada instalación o actualización de `dcasa_base` (y tras quitar los módulos sobrantes en el
arranque) se dejan así, de forma idempotente; si alguien las vuelve a encender, la siguiente
actualización las apaga de nuevo. Si la tienda activa la función (p. ej. configura un correo entrante o
enciende la asignación de iniciativas), Odoo vuelve a encender el cron por su cuenta.

| Acción planificada de Odoo | Qué se hace | Por qué |
|---|---|---|
| Mail: Fetchmail Service (cada 5 min) | apagada | no hay servidor de correo entrante |
| Publisher: Update Notification (semanal) | apagada | manda estadísticas anónimas de la instalación a Odoo S.A. |
| CRM: Lead Assignment (diaria) | apagada | no se usan reglas de asignación por equipo |
| Predictive Lead Scoring (diaria) | pasa a **semanal** | pocas iniciativas: basta recalcular una vez por semana |
| CRM: enrich leads (IAP) | apagada | servicio de pago de Odoo que no se contrata |
| Digest Emails (diaria) | apagada | correos de KPI que nadie pidió |
| Users: Notify About Unregistered Users (diaria) | apagada | recordatorios por correo a usuarios invitados; no se invita por correo |
| Calendar: Event Reminder (diaria) | apagada | el calendario está oculto |
| SMS Queue Manager, Snailmail (diarias) | apagadas | SMS y correo postal de pago; además esos módulos se desinstalan |
| eCommerce: abandoned cart email (cada hora) | pasa a **diaria** | el CTA es WhatsApp y la opción está apagada en Ajustes del sitio |

Los crons propios (respaldos, caché del borde, factura electrónica, sesiones, recolección de adjuntos en
R2, Socios, purga de accesos, depuración y vigilancia) **no se tocan**. La lista vive en
`CRONS_ODOO` (`addons/dcasa_base/models/mantenimiento.py`), con test.

## Tienda rápida (caché de páginas en el borde)

La portada, el catálogo (`/shop`, categorías y páginas), las fichas, Black Weekend, Visítanos,
Privacidad y Términos se pueden servir **desde el borde de Cloudflare** a los visitantes anónimos en
vez de pedírselas a Odoo cada vez. Es **la misma página que dibuja Odoo**, guardada tal cual: mismo
navbar píldora, héroe, footer y diseño (no hay una segunda plantilla que mantener). Quien entró con
usuario, tiene carrito o lista de deseos, o es socio con sesión, recibe siempre la página de Odoo
(con su carrito y su menú). El carrito, el pago, `/my`, `/socios` y el panel siempre son de Odoo.

**Cómo se mantiene al día.** Cada cambio que se ve en el sitio (precio, nombre, publicar/despublicar,
fotos, categorías, existencias, una venta o factura, ajustes del sitio, ediciones con el constructor
de sitios, menú, tarifas, Black Weekend) deja una marca en Odoo; a los ~20 segundos Odoo avisa al
Worker, que da por viejas todas las páginas guardadas y vuelve a pedir la portada, `/shop`,
`/black-weekend` y las fichas que cambiaron (las demás, con la primera visita). Otros centros de datos
de Cloudflare pueden tardar ~1-2 min más. Además, ninguna página se sirve sin pedirla de nuevo a
Odoo pasada una hora.

**Qué pasa si Odoo se reinicia (despliegue, caída, reinicio del host).** El borde guarda, junto con
cada página, lo que esa página necesita para verse bien: los estilos, el JS, las fuentes, el logo y la
foto principal. Mientras el contenedor arranca (~1 min), la portada, el catálogo y las fichas que ya
estaban guardadas salen **enteras** del borde y nadie nota nada; lo que no estaba guardado (una ficha
que nadie visitó, el carrito, pagar) recibe la página de «Estamos abriendo la tienda», que se recarga
sola. Si a una página guardada le faltaran los estilos en el borde (p. ej. Odoo no los pudo dar cuando
se guardó), el borde prefiere mostrar esa misma página de espera antes que una página sin estilos:
**nunca** debe verse rota. En `https://<sitio>/__edge/health`, el campo `tienda.sobrevive_reinicio`
dice si en este momento la portada y el catálogo saldrían enteros del borde (`rutas` detalla cada una:
`completa`, `sin_assets`, `vieja`, `falta`). Tras un despliegue, Odoo avisa al abrir y el borde vuelve
a guardar las páginas con los estilos nuevos; los viejos se borran solos a los 30 días. Costo: dentro
de lo incluido en el plan de Workers (estimación en `edge/CONTRATO_CONTENEDOR.md` §5).

**Encenderla:**

1. Cargar el secreto `TIENDA_FEED_TOKEN` (§5: `openssl rand -hex 32`, uno distinto por entorno) en
   GitHub → Environments → `staging` (y luego `production`).
2. El token de despliegue de Cloudflare necesita además el permiso **Workers KV Storage: Edit**
   (el primer despliegue crea solo el almacén «TIENDA» de cada entorno).
3. Desplegar. Staging viene con `TIENDA_ESTATICA = "on"`: abrir `https://<staging>/`, `/shop` y una
   ficha en una ventana privada; la cabecera `X-Dcasa-Cache: HIT` (o `MISS` la primera vez) confirma
   que salió del borde, también en el CSS (`/web/assets/…`) y las fuentes de la pestaña Red. Con
   sesión iniciada la página debe decir `BYPASS`. Staging nunca se indexa en Google (`X-Robots-Tag:
   noindex` en todas sus respuestas). Prueba de fuego: reiniciar el contenedor (o desplegar) y abrir
   la portada en el celular mientras arranca: debe verse igual que siempre.
4. Para producción: cambiar `TIENDA_ESTATICA` a `"on"` en `edge/wrangler.jsonc` (raíz) y desplegar.
   Para apagarla: `"off"` y desplegar; todo vuelve a salir de Odoo al instante.

**Si algo se ve viejo:** forzar la invalidación
`curl -X POST -H "Authorization: Bearer <TIENDA_FEED_TOKEN>" https://<sitio>/__edge/tienda/regenerar`.
Si el Worker no puede leer el almacén, la página la da Odoo (nunca una página en blanco). Logs:
eventos `paginas_invalidadas`, `paginas_precalentadas` (con cuántas páginas y assets), `pagina_retenida`
(se dio la página de espera porque faltaban estilos y Odoo no estaba), `pagina_lectura_fallida`,
`pagina_escritura_fallida`, `asset_lectura_fallida`, `asset_escritura_fallida`,
`asset_precalentar_fallido`.

## El sitio se edita por código

El sitio (`dcasapty.com`) **se construye y se cambia solo desde el repositorio** (`addons/website_dcasa`)
y llega con cada despliegue. Odoo trae además un constructor de páginas («Sitio web → Editar», «Nuevo
→ Página», galería de plantillas); en D'CASA **está apagado a propósito**. El porqué, en lenguaje llano,
está en [auditoria/ronda7/constructor-web.md](auditoria/ronda7/constructor-web.md). En corto: al guardar
una página con el constructor, Odoo hace una copia de esa página para el sitio y, desde entonces, lo
que llegue por código ya no se ve en ella (las dos versiones chocan y gana la copia).

**Lo que queda en el panel (menú «Sitio web», solo Gerencia):**

| Entrada | Para qué |
|---|---|
| **Vista previa móvil** | el sitio tal como lo ve un visitante, en un marco de teléfono (390×844), tableta (768) o escritorio (1440). Atajos a Inicio, Tienda, Socios y Visítanos, cualquier dirección a mano, «Recargar» y «Abrir aparte». También desde el Inicio: botón **Ver en el celular**. Nunca abre el modo edición |
| Sitio → Contenido → **Páginas** | ver las páginas y **publicarlas o despublicarlas**; al pulsar una fila se abre en la vista previa móvil. Nombre, dirección y contenido vienen del código; el título y la descripción para Google solo los puede cambiar un administrador (Odoo los guarda en la vista) |
| Sitio → Contenido → **Productos** y eCommerce → **Productos** | publicar/despublicar productos en la tienda, fotos, descripciones, categorías: esto sí es trabajo del día a día |
| eCommerce → **Pedidos** | pedidos, carritos abandonados y clientes de la tienda en línea |
| Reportes → **Ventas en línea** | lo vendido por la tienda |
| **Configuración** (solo administradores) | el WhatsApp del sitio, medios de pago, entregas |

Lo que **no** está: Editar, Nueva página, editor de menús, propiedades/SEO/HTML de «esta página»,
páginas técnicas, temas y bloques, y los reportes de visitantes (la tienda se sirve desde la caché de
Cloudflare, así que Odoo no ve a los visitantes anónimos: las visitas se miran en el panel de Cloudflare).

**Cómo se sostiene (módulo `dcasa_interfaz`):**

1. **Nadie tiene los grupos «Sitio web / Editor» ni «Editor y diseñador»**, ni la dueña. Odoo se los da
   solo a `admin` y a todo administrador (Ajustes); el módulo los retira **en cada actualización**
   (`dcasa.sitio._sitio_por_codigo`, idempotente), también de los roles Vendedora y Gerencia. Sin esos
   grupos, Odoo no muestra «Editar» ni «Nuevo» en ninguna parte (ni en el sitio ni en el panel).
2. **Guarda de seguridad.** Aunque alguien consiguiera el grupo, las plantillas de D'CASA
   (`website_dcasa.*`, `dcasa_*.*` y la portada `website.homepage`) no admiten copias por sitio ni
   ediciones desde el panel: Odoo responde «Esta página se mantiene desde el código y no se edita desde
   aquí: pide el cambio a quien mantiene el sitio». Las copias que Odoo hace por su cuenta (al instalar:
   `website.homepage` y la portada de D'CASA que hereda de ella; las opciones de la tienda de
   `website_sale`) no se tocan, y nada de esto frena instalar o actualizar módulos (corren como
   superusuario). Solo frena a una persona en el panel; `sudo()` y las funciones de datos pasan.
3. Los menús del constructor se cuelgan del grupo «Editor y diseñador»: si algún día se le devuelve a
   alguien, vuelve todo junto.

**Cómo comprobarlo:** Ajustes → Usuarios → cualquier usuario → pestaña de permisos: en «Sitio web» no debe
haber nada marcado. Si alguien ve «Editar» o «Nuevo» en el panel, es que tiene el grupo: una
actualización del módulo (`make update` o el despliegue) se lo quita.

**Si algún día la dueña quiere el constructor (no recomendado mientras el sitio se mantenga por código):**

1. Ajustes → Técnico → Parámetros del sistema → crear `dcasa_interfaz.sitio_editable` = `1` (apaga la
   guarda del punto 2; con `0` o borrándolo vuelve).
2. Ajustes → Usuarios → la dueña → pestaña de permisos → **Sitio web: Editor y diseñador**. Dura hasta la
   siguiente actualización del módulo (que lo retira); para que sea permanente hay que quitar esa regla
   del código (`addons/dcasa_interfaz/models/sitio.py`) o cambiar la política.
3. Avisar a quien mantiene el sitio: toda página guardada con el constructor deja de recibir los cambios
   del código hasta que se borre su copia por sitio (Ajustes → Técnico → Vistas, filtro «Sitio web»).

## Dónde ver los logs

| Qué | Dónde |
|---|---|
| Lo que pasa en el sitio (arranques, caídas, respaldos) | Panel de Cloudflare → *Workers & Pages* → `dcasa` (o `dcasa-staging`) → **Logs**. Buscar eventos `arranque_listo`, `arranque_fallido`, `contenedor_detenido`, `respaldo` |
| El contenedor (Odoo y PostgreSQL por dentro) | Panel → *Workers & Pages* → **Containers** → `dcasa-odoocontainer` → instancias y logs. Para no gastar eventos de log, en producción Odoo escribe solo avisos y errores (`ODOO_LOG_LEVEL`, por defecto `warn`; staging `info`), no escribe una línea por visita (`werkzeug:WARNING`) y PostgreSQL no anota los *checkpoints*. Las métricas de D'CASA (`DCASA_METRICA`, `DCASA_LIMPIEZA`, `DCASA_ALERTA`) y la línea `"evento": "memoria"` salen igual. Para depurar: variables `ODOO_LOG_LEVEL=info` y `ODOO_LOG_HANDLER=werkzeug:INFO` |
| Alertas por Telegram | En el chat del bot de Brian (ver «Alertas por Telegram»). En los logs: Odoo deja `DCASA_ALERTA …` y en Ajustes → Técnico → Registros (`dcasa.alerta`); el Worker deja `alerta_telegram` (enviada o no), `alerta_sin_canal` (falta `DCASA_ALERTA_TELEGRAM_CHAT`) o `alerta_telegram_fallida` |
| Memoria real del contenedor | Buscar `"evento": "memoria"` en los logs del contenedor: una línea ~3 min después de cada arranque (`momento: arranque`) y otra cada vez que Odoo se cae (`odoo_caido`). `cgroup.anon` = memoria que de verdad usan los procesos; `cgroup.file` = caché de disco (el kernel la libera sola; el gráfico del panel puede incluirla); `procesos.odoo` / `procesos.postgres` = RSS y PSS (la PSS de PostgreSQL es la buena: la RSS cuenta `shared_buffers` en cada proceso); `cgroup.eventos.oom_kill` > 0 = el kernel mató un proceso por falta de memoria. También va dentro del reporte mensual (`DCASA_METRICA`) |
| Depuración y tamaños del mes; disco y memoria cada hora | Logs del contenedor: `DCASA_LIMPIEZA`, `DCASA_METRICA`, `DCASA_ALERTA`; o en Odoo: Ajustes → Técnico → **Registros** |
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

## Contrato visual de la cabecera y del hero (pedido de la dueña: «que este navbar nunca más se vuelva a dañar»)

El diseño aprobado de la píldora de vidrio líquido y del hero de la portada está fijado en un test
que abre el sitio en Chrome a 1440 y 390 px (`addons/website_dcasa/tests/test_contrato_visual.py`),
en las cinco páginas tipo: `/`, `/shop`, una ficha, `/socios` y `/black-weekend`. Tiene dos niveles:

| Nivel | Qué mide | Falla cuando… |
|---|---|---|
| **Estilos computados** (bloqueante, siempre) | `.o_main_nav::before`: `backdrop-filter` con `blur(` y `saturate(`, tinte `rgba(255,255,255,.62)` con texto tinta (vidrio claro: tienda, ficha) o `rgba(0,0,0,.26)` con texto blanco (ahumado: portada, socios, Black Weekend), radio de píldora `32px`, filos de luz, **los mismos valores en todas las páginas del mismo tipo**; hamburguesa visible en el celular. Hero de la portada: `.o_dcasa_hero_texto` sin fondo, texto blanco con halo, velo negro plano del 35-50 %, nada azul ni navy detrás del titular | cualquier valor se sale del contrato. No depende de la versión de Chrome ni de las fuentes del sistema: si falla, el navbar o el hero cambiaron de verdad |
| **Píxeles contra las referencias** | capturas de la cabecera (todas las páginas) y del hero (portada, a media resolución) contra `addons/website_dcasa/tests/referencia/*.webp` (sin pérdida). Cuenta los píxeles con una diferencia > 40/255 en algún canal | superan la tolerancia: **1,5 %** en local, **6 %** en CI (`CI=true`); `DCASA_TOLERANCIA_VISUAL` manda sobre ambas |

Las capturas son deterministas: viewport fijo, `prefers-reduced-motion: reduce`, animaciones y
transiciones apagadas, `document.fonts.ready`, fotos de la cabecera y del hero cargadas, barra de
desplazamiento oculta, cabecera ya medida por el observador del sitio.

**Regla: cambiar la cabecera o el hero exige regenerar las referencias en el mismo commit.**

```bash
scripts/actualizar_referencias_visuales.sh          # usa scripts/test.sh con DCASA_REFERENCIAS_VISUALES=regenerar
git add addons/website_dcasa/tests/referencia       # y se suben junto con el cambio de SCSS/plantilla
```

El script corre primero el contrato de estilos: si el navbar o el hero rompieron el contrato, falla y
no reescribe nada. Antes de subir las capturas, míralas: son lo que verá la dueña.

Cuando el test de píxeles falla, deja la captura actual y la máscara de diferencias en la carpeta de
capturas de Odoo (`screenshots/…/contrato_visual/visual_*_actual.png` y `*_diff.png`; la ruta sale
en el log) para ver qué se movió.

Por qué los píxeles no son el nivel bloqueante: el rasterizado del texto, el antialiasing y el
desenfoque del vidrio cambian entre versiones de Chrome y entre sistemas (el Chrome del runner de
GitHub no es el Chromium local), y una diferencia de un píxel en el borde de cada letra ya mueve
el 1-2 % de la cabecera sin que el diseño haya cambiado. Por eso el contrato de estilos computados
es el que garantiza el diseño, y los píxeles son la red de seguridad contra lo que los estilos no
ven (una foto distinta, un elemento que se coló encima, una placa dibujada por otra regla). En CI
(`CI=true`) la tolerancia por defecto es del 6 %; en local y al regenerar, del 1,5 %. Si en CI la
diferencia es consistentemente alta sin cambio de diseño, regenera las referencias desde el
runner (`DCASA_TOLERANCIA_VISUAL` solo sube el umbral, nunca apaga la comparación).

## Contrato visual de la pantalla de Conversaciones de Juan

La pantalla de Conversaciones (y Resumen, Costos de IA y Conexiones) tiene su propio contrato, con el mismo método que la cabecera del
sitio: `addons/dcasa_conversaciones/tests/test_panel_visual.py`, medido en Chrome a 1440 y 390 px.

| Nivel | Qué mide | Falla cuando… |
|---|---|---|
| **Estilos computados** (bloqueante) | Sistema plano: ningún degradado, ninguna sombra de texto, ninguna sombra de más de 16 px de desenfoque ni 8 px de caída. El amarillo `#FED00F` solo sobre azul marino (nunca texto, ícono ni fondo amarillo sobre un fondo claro). Contraste del texto de al menos 4,5:1 (3:1 si es grande). **Foco visible con Tab de verdad** (`:focus-visible` con contorno o anillo) en cada control | un estilo nuevo se sale de la marca o de la accesibilidad. No depende de la versión de Chrome |
| **Píxeles contra las referencias** | la lista, un hilo abierto y Conexiones, a 1440 (media resolución) y 390 px, contra `addons/dcasa_conversaciones/tests/referencia/panel-*.webp` (sin pérdida), con la misma tolerancia que el contrato del sitio (**1,5 %** local, **6 %** en CI, `DCASA_TOLERANCIA_VISUAL` manda) | el diseño cambió de verdad |

Las capturas son deterministas: reloj del navegador fijo (10 de marzo de 2026, 10:00 en Panamá) y mensajes fechados respecto a él, viewport
fijo, `prefers-reduced-motion: reduce`, sin animaciones, sin barras de desplazamiento y fuentes e imágenes cargadas.

**Cambiar la pantalla exige regenerar las referencias en el mismo commit:**

```bash
scripts/actualizar_referencias_visuales_juan.sh      # scripts/test.sh con DCASA_REFERENCIAS_VISUALES=regenerar
git add addons/dcasa_conversaciones/tests/referencia
```

Las capturas que se le enseñan a la dueña (las ocho pantallas, escritorio y celular, con el catálogo real de la base) se generan
con `DCASA_CAPTURAS_JUAN=docs/auditoria/ronda7/capturas TEST_TAGS=/dcasa_conversaciones:TestContratoVisualJuan.test_capturas_para_la_duena scripts/test.sh dcasa_conversaciones`
y se llaman `juan-panel-<pantalla>-<escritorio|celular>.webp`.

## Inicio: accesos directos, panel por rol y «vendido» (pedidos de la dueña, 2026-10-10 y 2026-10-14)

### Los accesos grandes

Al abrir el panel, arriba del tablero hay accesos grandes, **en este orden**: **Productos** (la lista, con stock,
precio y categorías ordenables: `docs/CATALOGO.md`), **Facturas** (las facturas a clientes: la misma lista de
Facturación › Clientes › Facturas), **Conversaciones** (el chat de Juan; muestra cuántas hay sin leer),
**Oportunidades** (a quién escribirle hoy) y **Resumen contable** (dinero, deudas y utilidad; solo para Gerencia,
administradores y contabilidad: el mismo permiso del menú Reportes contables). Cada uno sale solo si la persona tiene
permiso y el módulo está instalado (`dcasa_interfaz`, `models/tablero.py › _atajos`). Para agregar otro acceso: una
entrada más en `_atajos` con el `xml_id` de la acción y un test en `addons/dcasa_interfaz/tests/`.

### Qué ve cada rol en el Inicio

| | Vendedora | Gerencia, administradores y contabilidad |
|---|---|---|
| Cifras | **Vendido hoy** (solo lo que ella vendió: «1 venta tuya», sin ITBMS) y **Mis cotizaciones** (las suyas abiertas). Sin ganancia ni costos | Franja de atención, **Ventas** con el interruptor **Facturado · Con abonos · Completadas** (sobre las facturas, como Contabilidad) y el selector Hoy · Semana · Mes · rango (sin ITBMS, con su desglose), **ganancia**, el bloque **Comparar** y el selector de **vendedora** (estos tres, solo Gerencia y administradores), Cotizaciones y Entregas lado a lado, pedidos web, por cobrar, socios (de toda la tienda), barras de la semana, caja y lo más vendido |
| Botones de arriba | ¿Qué necesito hacer?, **Nueva cotización** (el principal), **Nuevo cliente** | Los mismos y además Registrar cobro y Ver la tienda (solo ícono). Todos azules |
| Accesos grandes | Productos · Facturas · Conversaciones · **Escáner** | Productos · Facturas · Conversaciones · **Escáner** · Oportunidades · Resumen contable |

La vendedora **no** ve lo que está por cobrarse ni lo cobrado hoy: cobra desde la factura, no desde el Inicio. «Panel
completo» es quien tiene Ventas administrador, contabilidad (lector contable o más) o es administrador técnico; «solo lo
propio» es quien tiene Ventas pero no es de esos (`dcasa.tablero._solo_lo_propio`). Quien no vende (no tiene Ventas)
no cambia: ve lo que su permiso deje.

### ITBMS, costo y ganancia en el Inicio (criterio contable, 2026-10-16)

- **Ventas, costo y ganancia van sin ITBMS**: el ITBMS no es ingreso de la tienda, es plata que se le entrega a la DGI. El
  **dinero que se mueve** (por cobrar, cobrado, caja) va **con** ITBMS porque es lo que de verdad entra o se debe.
  Cada cifra lo dice en su etiqueta («sin ITBMS» / «con ITBMS») y la tarjeta de ventas trae el desglose
  *sin ITBMS · ITBMS · total*.
- **Ganancia = venta neta − costo**, ambas sin ITBMS. El costo de cada línea se **guarda al confirmar la venta**
  (`sale.order.line.dcasa_costo_unitario`, `dcasa_base/models/utilidad.py`): si el costo del producto cambia después, las
  ventas ya hechas no se mueven. Solo cuentan las líneas de mercancía (el flete no) y los descuentos. Un pedido con
  mercancía **sin costo cargado** no inventa ganancia: queda fuera y el Inicio lo avisa («N productos vendibles no
  tienen costo cargado»). Las ventas anteriores a este cambio toman el costo de hoy del producto al actualizar el módulo.
- **Quién la ve:** Gerencia y administradores (`GRUPOS_UTILIDAD`). La Vendedora no ve el costo ni la ganancia de las
  ventas (ni en el Inicio, ni en Estadísticas, ni en las líneas de venta, ni en Brian). El campo «Costo» **de la ficha del
  producto** es de Odoo y sigue visible para el personal interno: ver el último párrafo de «Costos y ganancia» en
  [PERMISOS.md](PERMISOS.md). No se instaló `sale_margin` a propósito: mostraría el costo a todo el personal.
- **Selector de periodo:** Hoy, Esta semana (lunes a hoy), Este mes (del 1 a hoy) o un rango de hasta un año. Las
  comparaciones ya no van en frases debajo de la tarjeta: viven en el bloque **Comparar** (abajo). Servidor:
  `dcasa.tablero.ventas_del_periodo(periodo, desde, hasta, base, vendedor)`.
- **Estadísticas** (menú aparte, solo Gerencia y administradores): *Lo más vendido*, *Mejor margen* y *Lo que no se
  mueve* (con existencias y sin ventas en 90 días).
- **Stock bajo:** la franja de atención avisa de los productos con 5 unidades o menos (parámetro
  `dcasa.stock_bajo_umbral`).
- **Envíos** aparece en el menú como «En desarrollo» mientras se define el servicio (`dcasa_contabilidad`,
  `static/src/js/en_desarrollo.js`).

### Facturado, Con abonos o Completadas, y Comparar (Inicio de Gerencia, 2026-10-17)

Pedido del jefe, aprobado por la dueña: la administración quiere **números, no texto**, y el Inicio cuenta las ventas
**sobre las facturas, igual que Contabilidad** (decisiones A1 y A2 de [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md):
«vendido» son todas las facturas publicadas, el día de la factura, y debajo cuántas salieron de un pedido de una
vendedora). Código: `addons/dcasa_interfaz/models/ventas_bases.py` (qué facturas cuentan y cuándo) y `models/comparar.py`
(el bloque); pruebas en `tests/test_facturado.py` y `tests/test_comparar.py`.

**El interruptor «Facturado» · «Con abonos» · «Completadas»** (arriba de Ventas; abre en **Facturado**). Las tres parten
del **mismo conjunto: las facturas de cliente publicadas**, con las facturas hechas directo (sin pedido) y las del
sistema anterior. Las **notas de crédito restan**, como en Contabilidad. Montos sin ITBMS, con el ITBMS y el total
aparte. Debajo, una línea corta dice qué se cuenta. Cambia a la vez **todo lo que habla de ventas en el Inicio de
Gerencia**: las tarjetas de Ventas y de Ganancia (con su número de facturas y la lista que abren, que es exactamente el
mismo conjunto), todo el bloque Comparar (también «Mes ▾»), «Por vendedora», la gráfica **Ventas de la semana**, **Lo
más vendido** y **Vendido hoy** (es la tarjeta de Ventas en «Hoy»). La gráfica y lo más vendido dicen en su título qué
posición y qué vendedora muestran.

| | Qué cuenta | En qué día |
|---|---|---|
| **Facturado** | **Todas** las facturas publicadas; las notas de crédito restan. Es lo mismo que las «Ventas» de Contabilidad (el Estado de resultados) para esas fechas. Debajo: «N de M salieron de un pedido de una vendedora» | El de la factura (su fecha contable, la misma que usa Contabilidad) |
| **Con abonos** | Las facturas con **al menos un pago** (completas o a medias), **por su valor total**. Trae **Falta por cobrar**: el saldo de esas facturas, con ITBMS (el dinero real que falta), como el que ve el cliente, al cierre del periodo | El de la factura |
| **Completadas** | Las facturas **pagadas al 100 %** (también «en proceso de pago») | El del pago que dejó el saldo en cero (nunca antes de la factura) |

- **Para que la dueña cambie con cuál abre** es una línea: `BASE_POR_DEFECTO` en `addons/dcasa_interfaz/models/tablero.py`
  (Brian usa la misma si no se le pide otra).
- **Notas de crédito.** En «Facturado» restan el día de la nota, como en Contabilidad. En las otras dos restan solo si su
  factura cuenta ahí (en «Con abonos», si su factura tiene un abono; en «Completadas», si está pagada al 100 %, el día más
  tardío entre el de la nota y el que se completó la factura). Así una devolución entera saca la venta (una factura
  anulada con su nota queda «revertida»: no tiene pagos) y una parcial resta solo lo devuelto. Su factura es la que
  revierte o, si la nota se hizo aparte, la factura con que se concilió; una nota sin factura solo resta en «Facturado».
- Ejemplo de la dueña (está en las pruebas): sofá de $1,000 facturado el 5 de octubre, abono de $200 ese día y el resto
  el 20 de noviembre. Facturado: octubre $1,000. Con abonos: octubre $1,000 con $800 por cobrar; noviembre $0.
  Completadas: octubre $0, noviembre $1,000. Cobrado: octubre $200, noviembre $800. Una factura sin pedido entra igual,
  según su caso.
- El día del último pago sale de las conciliaciones de cada factura (las mismas que lista su cuadro de pagos,
  `account.move._dcasa_pagos()` de `dcasa_invoice`), leídas de una vez para todo el periodo.
- **«Contabilidad dice…»** ya no es una línea larga a la vista: es un ícono **ⓘ** junto al título «Ventas» que solo sale
  cuando el Inicio se aparta de Contabilidad, y al tocarlo dice la resta exacta, por qué y abre las facturas que la
  explican. En «Facturado» no sale, porque es lo mismo (saldría solo si algo que no es una factura de cliente tocara los
  ingresos, por ejemplo un asiento a mano: entonces lo dice y lo abre). En «Con abonos» explica las facturas sin ningún
  abono; en «Completadas», las que aún deben algo y las de otras fechas que se terminaron de pagar en el periodo. Solo
  con «Todo el equipo».
- **La explicación de la ganancia** («venta menos el costo de la mercancía, no resta gastos» y qué costo usa cada venta)
  también pasó a un **ⓘ** junto a «Ganancia bruta». A la vista quedan el monto, el porcentaje y, si hay, el aviso corto
  «N facturas tienen mercancía sin costo y no cuentan aquí». Los ⓘ son botones: se abren tocándolos (también con el
  teclado y en el celular), «Escape» o tocar fuera los cierra.
- **La vendedora no cambia:** su Inicio sigue con lo facturado por completo de sus pedidos, el día de la factura, sin
  interruptor, sin ⓘ y sin gráfica. Tampoco cambian el bono por meta de ventas (usa lo cobrado) ni el menú **Ventas ›
  Hoy › Ventas de hoy**, que es una lista de pedidos de la app Ventas (no es del Inicio).

**El selector de vendedora** (al lado del interruptor; abre en «Todo el equipo»): cada vendedora (quien tiene el rol
Vendedora sin ser Gerencia, tuvo ventas en los últimos 24 meses o figura como «Vendedor» de una factura sin pedido de esos
meses) y «Sin vendedora». Filtra las tarjetas, todo Comparar, la gráfica de la semana y lo más vendido. **De quién es
cada factura:** si salió de un pedido, del «Vendedor» del pedido (como siempre); si se hizo directo, del «Vendedor» de la
factura; sin ninguno, de «Sin vendedora» (ventas de la web o de Juan que nadie tomó). Una nota de crédito es de la
vendedora de la factura que devuelve (Odoo le pone a quien la hace, que es Gerencia). Ojo: si no se elige otro, Odoo pone
como «Vendedor» de una factura directa al vendedor del cliente o, si no tiene, a quien la crea (por ejemplo, Caja). Las
facturas del **sistema anterior** van a «Sin vendedora»: el archivo no trae la vendedora y Odoo les pondría a quien las
cargó (lo mismo si el «Vendedor» es el usuario del sistema, OdooBot). El **Cobrado** de una vendedora son los pagos
aplicados a **sus** facturas, no los que ella registró (Caja registra muchos); un anticipo suelto cuenta en el equipo,
pero no es de nadie. Falta por cobrar, igual: el saldo de sus facturas.

**La ganancia de una factura** es la venta sin ITBMS menos el costo de la mercancía, línea por línea, con la misma regla
de los pedidos: la mercancía y las rebajas (descuento global, de importe fijo) cuentan; el flete y los demás servicios no.
El costo de una venta que salió de un pedido es el que el pedido guardó al confirmarse; el de una **factura sin pedido**
(también las del sistema anterior) es el **costo de hoy del producto**, la misma regla que ya usaban las ventas hechas antes
de esta pantalla. Una factura con mercancía sin costo (o con una línea sin producto que suma) no inventa ganancia: queda
fuera y se avisa; la franja de atención sigue avisando «N productos vendibles no tienen costo cargado».

**Comparar** (debajo de las tarjetas). Una fila de botones; cada uno es una comparación completa, A contra B:

| Botón | A | B |
|---|---|---|
| **Ayer** | Hoy | Ayer |
| **17 sep** (el mismo número de día del mes pasado) | Hoy | Ese día; el 31 contra el último día del mes pasado; el 29 o 30 de marzo, contra el último de febrero |
| **Sáb. 10 oct** (el mismo día, 7 días atrás) | Hoy | Ese día |
| **1–17 sep** | Del 1 a hoy | Los mismos días del mes pasado (hasta su último día si es más corto) |
| **Mes ▾** | Del 1 a hoy | Un mes completo que se elige (por defecto el pasado; los últimos 24). Arriba, un número grande: «Llevas 58 % de septiembre» (ventas de este mes ÷ ventas de ese mes), y la última columna es «Llevas» |
| **A vs B** | Un rango del calendario | Del mismo largo que A (solo se elige dónde empieza B); con «Libre», de cualquier largo |

- Al tocar un botón sale una tabla con solo números; las cabeceras son las fechas («17 oct», «1–17 oct», «Sep
  completo»). Filas: **Ventas** y **Ganancia** (sin ITBMS; las mismas de las tarjetas), **Margen** (ganancia ÷ venta de
  mercancía de esas mismas facturas: el porcentaje que ya muestra la tarjeta de Ganancia; su cambio va en puntos, «pts»),
  **N.º de ventas** (facturas; su cambio, en unidades; una nota de crédito resta del monto, no del número), **Falta por
  cobrar** (solo «Con abonos»; con ITBMS; que suba se pinta en rojo) y **Cobrado** (con ITBMS; igual en las tres
  posiciones: el dinero que entró).
- **Ticket promedio y unidades por tipo (K1, 2026-10-18):** debajo de Ventas, «Ticket promedio $X» (ventas sin ITBMS ÷
  N.º de ventas; «—» sin ventas) y al lado **Unidades vendidas** por tipo (la categoría de primer nivel del producto,
  p. ej. Salas, Recámaras, Colchones; sin flete, anticipos ni descuentos; las notas de crédito restan; de más a menos,
  pasados 8 tipos «Otros», y el Total). Siguen el interruptor, el periodo y la vendedora. En Comparar, la fila
  **Ticket promedio** con su % (con distinto largo no va por día; en «Mes ▾», «—»).
- **Azul si sube, rojo si baja.** Sin base positiva (cero o negativa) el porcentaje es «—»: nunca se inventa uno.
- **Distinto largo:** si A y B no tienen los mismos días (A vs B con «Libre», o el 31 contra un mes de 30), el
  porcentaje se calcula sobre el **promedio por día** y la cabecera dice «% por día».
- **«Por vendedora»:** una fila por vendedora con ventas A, ventas B y el cambio, de mayor a menor en A. Al tocar una,
  el selector queda en esa vendedora. En el celular se lee sin moverse de costado.
- **Hasta la misma hora (hora de Panamá):** si A termina hoy, hoy cuenta hasta la hora actual y el último día de B
  hasta la misma hora (el relojito de la tabla dice cuál). Así a las 11 de la mañana no sale todo en rojo. En «Mes ▾»
  B es un mes completo y no se corta. Los días anteriores al último cuentan completos.
- **Decisión sobre la hora (lo más honesto con lo que guarda el sistema):** una factura y un pago tienen fecha (el día
  del negocio), no hora. La hora que sí existe es la de **registro** (`create_date`: cuándo se anotó en el sistema). El
  corte cuenta **lo que a esa hora ya estaba registrado**, es decir, lo que el Inicio habría mostrado ese día a esa
  hora: una factura o nota, si ya estaba registrada (con abonos, también su primer abono); una factura completada, si el
  pago que la completó ya se había aplicado (`account.partial.reconcile.create_date`); un cobro, si ya estaba registrado
  (`account.payment.create_date`). Lo que se anota tarde (un pago de ayer registrado hoy, o lo que se cargue del sistema
  anterior) no tiene hora de ese día: cuenta en los días completos, pero no en el corte. En la tienda la factura y el
  cobro se hacen en caja al momento, así que la hora de registro es la de la venta.
- **Permisos:** el bloque, el selector de vendedora y la ganancia son de Gerencia y administradores
  (`_ve_utilidad`). El servidor lo exige en `dcasa.tablero.comparar_ventas` (AccessError) y rechaza un `vendedor`
  ajeno en `ventas_del_periodo` y en `grafica_de_ventas` a cualquier otro, aunque lo mande a mano. Valida también la
  comparación, la base, el mes, las fechas (no futuras, «desde» ≤ «hasta», hasta un año por rango). Las facturas se
  suman con `sudo` siempre filtrado a facturas y notas de crédito de cliente; la lista que abre cada cifra la ve cada
  quien con sus permisos.
- Brian responde «¿cómo vamos contra septiembre?» con las mismas cifras (`comparar_ventas`, [BRIAN.md](BRIAN.md)) y la
  Guía lo explica en «Comparar las ventas».

### Límites conocidos de las cifras del Inicio (revisión del 2026-10-16)

- **En el Inicio de Gerencia ya no quedan estos dos (2026-10-17):** cuenta las facturas publicadas, así que si en caja se
  corrige el precio de la factura cuenta lo de la factura, y una nota de crédito parcial resta solo lo devuelto.
  **Siguen en el Inicio de la vendedora** (que no cambió): «vendido» sale de los importes del pedido (cuadra cuando la
  factura es igual al pedido, lo normal) y una nota de crédito parcial saca el pedido entero de «vendido».
- **Ganancia de una factura sin pedido:** usa el costo de hoy del producto (no hay un costo guardado del día de la
  venta). Si el costo del producto cambia, cambia la ganancia de esas facturas.
- **La ganancia es una cifra de gestión**: venta menos el costo guardado de cada producto cuando se confirmó la venta. No es
  el costo de ventas contable (que se registra al entregar y puede usar otro método de costo); no se compara con el estado de
  resultados.
- **Ventas anteriores a esta pantalla:** al estrenarla tomaron el costo de hoy del producto, y las nuevas guardan el del día. La
  comparación con el mes pasado mezcla los dos criterios durante uno o dos meses.
- **Cobrado / Caja de hoy:** cuenta los pagos recibidos y confirmados (en proceso o pagados) con ITBMS; no cuenta borradores,
  cancelados ni rechazados.
- **«Esta semana»** va de lunes a hoy y «Este mes» del 1 a hoy. Las comparaciones (bloque Comparar) cortan el otro
  día a la misma hora y, si los periodos no tienen los mismos días, comparan el promedio por día (2026-10-17).
- **Lo más vendido** son los últimos 30 días corridos (no el mes calendario), de la posición del interruptor, y no cuenta
  servicios (flete, descuentos) ni anticipos; las notas de crédito restan las unidades devueltas.
- **Mejor margen** incluye el descuento global como su propia fila, para que el total cuadre con el Inicio. No cuenta la
  mercancía sin costo cargado.

### Qué cuenta como «vendido» y en qué día

Una **venta** es un pedido confirmado, **facturado por completo y con todas sus facturas publicadas**. Una cotización,
un borrador, un pedido «por facturar» (un apartado que aún no se cobra ni se entrega) o uno cuya factura sigue en
borrador **no** es venta. Odoo da por «facturado» también lo que está en una factura en borrador; por eso se exige,
además, que ninguna quede sin publicar.

El **día de la venta es el de su última factura publicada**, no el del pedido: el apartado del lunes que se cobra y se
factura el viernes se vendió el viernes, el mismo día que entra la plata a la caja, y el número de un día que ya pasó no
cambia solo. Una nota de crédito que devuelve todo saca la venta. El día se guarda en `sale.order.dcasa_fecha_venta`
(se calcula solo; al actualizar el módulo se calcula para los pedidos que ya existen) y la definición vive en
`sale.order._dcasa_dominio_vendido`. **Es la definición de la vendedora**: su tarjeta «Vendido hoy» y la lista que abre,
el menú **Ventas › Hoy › Ventas de hoy** y lo que Brian le responde (`resumen_ventas`). El **Inicio de Gerencia** cuenta
desde el 2026-10-17 las **facturas publicadas**, como Contabilidad (sección «Facturado, Con abonos o Completadas»), y
Brian le responde a Gerencia lo mismo.

**Factura suelta (sin cotización).** Una factura hecha directamente, sin pedido de venta detrás, y las facturas que vinieron
del sistema anterior **no son una «venta» del Inicio de la vendedora** (no hay pedido que contar), pero **sí cuentan en el
Inicio de Gerencia** (que cuenta las facturas, como Contabilidad, y dice cuántas salieron de un pedido). Tampoco **tienen
nota de entrega** (la entrega nace del pedido): «Imprimir documentos» imprime entonces solo la factura. Por eso la vendedora cotiza y la
factura se hace desde esa cotización en caja; cobrar y facturar es del personal administrativo. El dinero de una factura
suelta sí está en Contabilidad (facturas, cobros, Resumen contable); lo que no existe es el pedido. Ver
`docs/AUDITORIA_CONTABLE.md` (factura vs. venta vs. cobro).

**Orden de «Imprimir documentos».** El PDF junta, venta por venta y en este orden: **nota de entrega** (la hoja que se
despacha en bodega) → **factura del cliente** → **copia de la empresa**. Con varias ventas, el mismo orden se repite en
cada una. El orden vive en `DOCUMENTOS` (`addons/dcasa_invoice/wizard/impresion_paquete.py`) y no depende del orden en que
se marquen las casillas; una venta sin entrega (factura suelta) lleva solo la factura y la copia.

**El papel del abono (pedido de la dueña, 2026-10-16).** La contabilidad no cambia: en el primer abono se publica la
factura completa (con ITBMS) y cada abono es un pago parcial con **«Pagar»** de esa factura. Mientras la factura tenga
algo pagado y algo por pagar (`account.move._dcasa_es_abono`), el papel sale con el título **ABONO** (y el número de la
factura), un recuadro **SALDO POR PAGAR** bajo los totales con «Pagado $X de $Y», «Inicio del abono» y «El abono vence»
en los datos (en lugar del «Vence» de la condición de pago) y, si el plazo pasó, «El plazo venció el …» (solo se dice:
el sistema no calcula ni cobra nada). Las cifras salen de `_dcasa_estado_abono` (la misma fuente que «Mi cuenta», las
Condiciones, los correos y Brian); el plazo son **30 días continuos** desde el primer abono (decisión de la gerencia
A3, 2026-10-17; parámetro `dcasa_invoice.abono_dias`, 0 = no vence; antes era `abono_meses`, «un mes», y la migración
19.0.2.4.0 lo pasa a días). El **primer abono** es al menos la mitad del total: si es menos, solo Gerencia lo registra
(el asistente «Pagar» lo avisa; ver [PERMISOS.md](PERMISOS.md)). Pagada por completo vuelve a decir **Factura** con todos sus abonos;
las notas de crédito y las facturas de proveedor no cambian. El PDF se llama «Abono INV/…». Cada abono registrado con
«Pagar» ofrece el cuadro «Imprimir documentos» (si la empresa tiene encendido ofrecerlo) con la factura y su copia
marcadas y la **nota de entrega sin marcar**: se imprime al terminar de pagar (se puede marcar a mano). Un cobro anotado
suelto en Pagos no se une solo a la factura: los abonos se registran desde la factura. Código: `views/report_invoice.xml`
y `wizard/impresion_paquete.py`; pruebas: `tests/test_abono_papel.py` y `TestOfertaAlPagar` en `tests/test_paquete.py`.

**Condiciones de abono (`dcasa_abonos`, pedido de la dueña, 2026-10-17).** La hoja que la tienda ya entregaba en papel,
impresa con la marca de las facturas en **dos hojas por factura**: **COPIA CLIENTE** (la firma y se la lleva el cliente)
y **COPIA EMPRESA** (se queda la tienda; además del código público DC-… lleva la referencia interna). Cada una con el
cliente y su cédula/RUC si la ficha la tiene, el número de factura, inicio y vencimiento del abono, los muebles, total,
abonado y saldo (de `_dcasa_estado_abono`), las condiciones numeradas y las rayas de FIRMA DEL CLIENTE y NÚMERO DE
CÉDULA. El texto es la versión 1 de la hoja (7 condiciones) y se cambia en Ajustes › Empresas › «Documentos D'CASA»,
sección «Condiciones de abono» (una por renglón; vacío no se imprime; puesto una sola vez sin pisar cambios). En
«Imprimir documentos» es la casilla **«Condiciones de abono (2 copias)»**, marcada solo en el **primer** abono; el PDF va
ABONO → condiciones cliente → condiciones empresa → copia de la factura. **Cada copia cabe en UNA hoja**: con muchos
muebles solo se achica la tabla (`condiciones.ajuste_a_una_hoja`, medido sobre el PDF real) y en una factura enorme la
lista se corta con «Y N muebles más…»; el pie no lleva «Página 1 / 2». Solo imprime: la contabilidad no cambia.
Código y pruebas: `addons/dcasa_abonos/` (`tests/test_condiciones.py`, con el PDF de wkhtmltopdf).

El texto de las listas vacías propias (p. ej. «Todavía no hay ventas facturadas hoy») sale si el párrafo lleva la clase
`o_dcasa_ayuda`; sin ella, el panel muestra el aviso general «Aquí todavía no hay nada».

## Reponer: cuánto pedirle al proveedor (pedido del jefe 2026-10-19; ritmo y llegada, la dueña 2026-10-22)

**Compras › Reponer** (solo Gerencia y administradores; la Vendedora no la ve y el servidor se lo niega). Todo viene de
China y tarda meses: la pantalla dice, por producto, en cuánto tiempo se acaba y cuánto pedir para cubrir la llegada.
Es una pantalla propia (acción cliente `dcasa_reponer`), cómoda en el celular (cada fila es una tarjeta, sin scroll de
costado), en tres pasos:

1. **Elige el proveedor**: un buscador donde se escribe parte del nombre, el teléfono, el RUC o el nombre o código de
   un producto que vende (también su código en el proveedor). Cada resultado dice cuántos productos le compras, la
   última compra confirmada y cuánto tarda en llegar; se toca para elegirlo. «Todos los proveedores» siempre está.
2. **Elige cuánto mirar**: los meses de ventas (1 a 12; de fábrica **5**, el ejemplo de la dueña) y la **reserva**
   (meses extra por si acaso; de fábrica 0).
3. **Qué pedir**: la lista, **Por urgencia** (de fábrica) o **Por proveedor** (cada uno con su tiempo de llegada,
   su botón para ponerlo o cambiarlo y su total).

| Columna | De dónde sale |
|---|---|
| Vendido en N meses | Unidades de las **facturas publicadas** de los últimos N meses (hasta hoy) menos las notas de crédito: las mismas de «Lo más vendido» del Inicio (base «Facturado»). Sin servicios, flete, anticipos ni líneas sin producto. |
| Se vende al mes | Vendido ÷ N. |
| Hay hoy | Lo que hay en las ubicaciones internas. |
| Viene en camino | Compras **confirmadas** que todavía no se reciben (un borrador no cuenta). |
| Alcanza para | (Hay hoy + Viene en camino) ÷ Se vende al mes, en meses o días (un mes = 30 días). |
| Tarda en llegar | Los días de entrega del **precio de proveedor principal** (el primero de los precios del producto; campo `delay` de Odoo). |
| Pedir | Se vende al mes × (meses que tarda + meses de reserva) − Hay hoy − Viene en camino, hacia arriba, solo si da más de 0. |
| Aviso | **Pedir ya** si lo que hay y lo que viene no alcanza para lo que tarda en llegar; **Pedir**; **Falta el tiempo de llegada**; **Sin proveedor**; **Alcanza**. La lista va en ese orden y, dentro, lo que se acaba antes primero. |

- **Nunca se inventa el tiempo de llegada.** Odoo pone **1 día** solo en cada precio de proveedor (y la carga del
  sistema anterior, 0 si no venía el plazo): 0 o 1 día cuentan como **falta**, salvo que alguien lo haya puesto a
  propósito desde Reponer o Brian (marca `dcasa_llegada_puesta` del precio). Un plazo de más de 1 día puesto en la
  ficha del producto (pestaña Compra) sí cuenta. Sin el dato, la fila dice «Falta» y **no** calcula cuánto pedir.
- **Poner o cambiar el tiempo de llegada:** botón «Poner tiempo de llegada» (o «Cambiar») del proveedor elegido, de
  su grupo o «Poner» en la fila. Se escribe en **meses o días**; se guarda en **todos sus precios de proveedor** y queda
  anotado en la ficha del proveedor (quién y cuánto). De 1 día a 24 meses. Es el mismo campo con que Odoo calcula la
  **fecha de llegada esperada** de las compras nuevas a ese proveedor (y las reglas de reabastecimiento, si se usan):
  ponerlo bien también corrige esa fecha.
- **Producto sin precio de proveedor:** sale como «Sin proveedor», con su ritmo, pero sin cuánto pedir. Se arregla en la
  ficha del producto, pestaña **Compra** (agregar el proveedor con su precio); un proveedor sin ningún precio no puede
  tener tiempo de llegada (la pantalla lo dice).
- **Lo que no se vendió** en la ventana no sale (con un proveedor elegido, la pantalla dice cuántos productos suyos no
  se vendieron). Si un producto estuvo agotado, vendió menos y su ritmo sale más bajo: conviene mirarlo a ojo.
- **Descargar Excel** (Gerencia y administradores): el servidor arma el archivo (`/dcasa/reponer/excel`) con la hoja
  «Reponer» (lo mismo que la pantalla) y «Por proveedor» (totales). No hace falta abrirle a nadie el «Exportar» general
  de Odoo.
- Brian: `que_reponer(proveedor?, meses?, reserva?)` y `poner_tiempo_llegada(proveedor, dias? / meses?)`.
  Código: `addons/dcasa_interfaz/models/reponer.py`, `controllers/reponer.py`, `static/src/js/reponer.js`.

## Por día, Estadísticas y Movimientos (pedido del jefe y de la dueña, 2026-10-22)

Lo pedido: «tenemos estadísticas pero muy poco intuitivas y limitadas», «ver organizado fácilmente lo vendido o
facturado por día de los días del mes, poder ver fácilmente lo que se hizo x día» y «en inventario hay un historial de
movimientos pero también es muy poco intuitivo». Las tres pantallas son de **Gerencia y administradores** (el servidor
lo exige en cada llamada; la Vendedora no ve los menús ni recibe las cifras aunque las pida por la conexión de datos).

### Por día (Ventas › Hoy › Ventas por día · Facturación › Clientes › Facturado por día)

Una sola pantalla: abre en **Vendido** desde Ventas y en **Facturado** desde Facturación, desde Estadísticas › Por día y
desde el botón **Ver por día** del bloque de Ventas del Inicio (con la base y la vendedora que estén elegidas).

* **El mes como calendario** (lunes a domingo) en la computadora; en el celular, **una lista de días** del más reciente
  al primero. Cada día: lo vendido o facturado **sin ITBMS**, cuántas ventas o facturas (y notas de crédito) y una
  barrita del tamaño de lo de ese día. Los días que no han llegado van en gris.
* **Tocar un día** muestra (a la derecha, o debajo del día en el celular) su total sin ITBMS, el ITBMS y el total con
  ITBMS, y cada documento: cliente, número, vendedora, pedido de origen u hora de confirmación, monto y estado
  («Pagada», «Con abono», «Por cobrar», «Nota de crédito», «Por facturar»…). Tocar uno lo abre; «Ver en lista» abre
  todos en la lista de Odoo.
* Arriba: el **mes** (este y los 24 anteriores, con flechas), **qué contar** y la **vendedora**:
  * **Vendido**: los **pedidos confirmados**, el día **de Panamá** en que se confirmaron (un pedido confirmado a las
    11:30 p. m. cuenta ese día aunque en UTC ya sea el siguiente). Una cotización o un pedido cancelado no cuentan.
  * **Facturado**, **Con abonos** y **Completadas**: exactamente las del Inicio (facturas publicadas; las notas de
    crédito restan el día de su fecha; una factura anulada o en borrador no cuenta). El total del mes es el mismo
    número que la tarjeta de Ventas del Inicio para esas fechas y **los días suman el mes al centavo**.
* Tres tarjetas: el **total del mes** (sin ITBMS, con el ITBMS y el total con ITBMS aparte; abre la lista de lo que se
  contó), **contra el mes anterior** (si el mes está en curso, los mismos días del mes pasado con el último hasta la
  misma hora de Panamá: la misma cuenta que «Comparar › del 1 a hoy» del Inicio; si el mes ya terminó, el mes anterior
  completo; sin base, «—») y el **mejor día** con el ticket promedio.

### Estadísticas › Resumen

La app Estadísticas abre en **Resumen**: botones de periodo (esta semana, este mes, mes pasado, últimos 3 meses, este
año o fechas elegidas, hasta un año) y las mismas cuatro bases. Cuatro números con su frase (ventas sin ITBMS,
facturas o pedidos, ticket promedio y unidades) y gráficas planas en azul de la marca: **ventas por día** (o por mes
si el periodo pasa de 62 días; tocar una barra abre Por día en ese día o ese mes), **por tipo de producto** (la
categoría de primer nivel, como «Unidades vendidas por tipo» del Inicio; solo mercancía, sin flete ni descuentos
generales, por eso puede no sumar el total), **por vendedora** (suma el total) y **lo más vendido** (los 10 con más
unidades). Lo que el Inicio ya muestra bien no se repite: hay enlaces a **Por día**, **Comparar periodos** (Inicio),
**Mejor margen** y **Lo que no se mueve**, que siguen en el mismo menú (las tablas de antes siguen ahí para quien las
usa).

### Inventario › Movimientos

Se busca un producto por **nombre, código o código de barras** (el código o el código de barras exacto sale primero) y
se ve su **línea de tiempo en palabras**, de lo más nuevo a lo más viejo: «Entró por la compra P00012 de PROVEEDOR»,
«Salió por la venta S00123 a CLIENTE», «Ajuste de inventario (+2)» (con el nombre del conteo, p. ej. «Conteo con
lector (Ana)»), «Devolución del cliente … (de S00123)», «Devolución al proveedor …», «Se dio de baja (merma) …»,
«Traslado de Bodega a Tienda». A la derecha, lo que entró en **verde (+)**, lo que salió en **rojo (−)** y un traslado
sin signo (no cambia lo que hay en total); debajo, **lo que quedó** después de ese movimiento; quién lo registró (la
última persona que tocó la línea del movimiento: normalmente quien lo validó) y cuándo (hora de Panamá). Tocar la frase
abre la venta, la compra o la operación. Sin producto, los **últimos movimientos de todos** (tocar el nombre del
producto abre su historia). Filtros: fechas y tipo (compras, ventas, devoluciones, ajustes, traslados, otros).

**Lo que quedó** se calcula desde lo que hay hoy hacia atrás, y **solo se muestra si la historia cuadra**: la suma de
todos los movimientos del producto da exactamente lo que hay hoy en los almacenes (las mismas ubicaciones de
«Disponible» de Odoo). Si hubo existencias cargadas sin movimiento, la pantalla lo dice y no muestra esa columna:
nunca se inventa una existencia.

Brian responde lo mismo con `ventas_por_dia` y `movimientos_de_producto` ([BRIAN.md](BRIAN.md)). Código:
`addons/dcasa_interfaz/models/por_dia.py`, `models/movimientos.py` y `static/src/js/por_dia.js`, `estadisticas.js`,
`movimientos.js`; pruebas en `tests/test_por_dia.py`, `test_movimientos.py` y `test_pantallas_navegador.py`.

## La «Actividad» de los formularios arranca escondida (pedido de la dueña, 2026-10-15)

Odoo pone al lado de cada formulario (cotización, factura, ficha…) el panel de mensajes y notas («Creando un nuevo registro…»),
que roba un pedazo de la pantalla. Ahora arranca **escondido** y un botón **«Actividad»** (arriba, junto al engranaje) lo muestra
o lo esconde. Lo que cada persona elige se recuerda en su navegador (`localStorage`, `dcasa.actividad_visible`) y vale igual para
todos los formularios; sin almacenamiento (ventana privada) vuelve a arrancar escondido. No se borra ni se cambia nada: solo
cambia dónde se pinta el panel. Los diálogos y el visor de adjuntos (modo «COMBO») no se tocan.

Código: `dcasa_interfaz/static/src/js/actividad.js` (parche de `FormRenderer.mailLayout` y `FormController`) y
`static/src/xml/actividad.xml` (el botón). Prueba: `dcasa_interfaz/tests/test_actividad.py` (en Chromium: arranca escondida,
el botón la muestra y la recuerda). Si alguien ve una pantalla vieja (con «Nueva factura» o el panel de actividad abierto), basta
recargar con **Ctrl + F5**: el navegador guardó la versión anterior de los archivos.

## El CRM se ajusta solo (acción planificada)

Cada 15 minutos corre **«Juan: ajustar el CRM»** (`crm.lead._dcasa_cron_crm`, módulo `dcasa_conversaciones`): lee las
oportunidades que nacieron de una conversación y aplica las reglas fijas de `docs/CRM_AUTOMATICO.md` (cotizada, ganada,
temperatura, sin respuesta). Cada oportunidad se procesa aparte: un error se escribe en el registro del servidor
(«CRM automático: falló …») y no frena a las demás. Para apagarlo sin tocar código: *Conversaciones › Configuración ›
Ajustes de Juan › El CRM se ajusta solo*. Si hay más de 500 oportunidades pendientes, el log avisa que ese turno revisó solo
las 500 más nuevas.


## «No disponible» de las vendedoras se reinicia cada mañana (acción planificada)

Cada hora corre **«Juan: volver a poner «Disponible» a las vendedoras cada mañana»** (`dcasa.reparto._cron_reiniciar_disponibilidad`,
módulo `dcasa_conversaciones`; detalle en `docs/JUAN_PANEL.md`). Pasado el corte de hoy (dos horas antes de la apertura de Ajustes de Juan: 6:00 a. m. de
Panamá con el horario de 8:00), deja «Disponible» a quien se marcó «No disponible» antes del corte, sin tocar a quien Gerencia sacó del reparto. Si el
contenedor estuvo dormido (staging) corre al despertar y no borra pausas marcadas después del corte.


## Apartados: cuánto duran y qué pasa si el cliente no llega (decisión de la dueña, 2026-10-09 y 2026-10-10)

Un «apartado» es un **pedido** de Odoo (no una factura: la factura nace al cobrar o entregar). Hay dos formas:

* **De la tienda web.** Con «Pago al recibir o en la tienda» el pedido se confirma solo y reserva el inventario; con
  transferencia o Yappy queda como cotización enviada. En cuanto queda por cobrar recibe una fecha:
  **hoy + 7 días** (*Ajustes › Sitio web › Apartados de la tienda*; **0 = nunca vence**).
* **A mano** (WhatsApp, mostrador). La vendedora pulsa **«Apartar»** en el pedido (enviado o confirmado) y cuenta los
  mismos días. Un pedido hecho a mano **sin** ese botón es una venta normal y no vence nunca. Si ella confirma un
  apartado a mano, la fecha se queda (la puso ella); si confirma un pedido de la web, la fecha se borra (lo tomó ella).

**Si el cliente no llega.** Cada noche a las 2:00 a. m. de Panamá (acción planificada «anular apartados que nadie
reclamó», `sale.order._dcasa_cron_vencer_apartados`) se anula todo pedido con fecha vencida: se cancela la entrega (el
inventario vuelve a quedar libre), si usó puntos de un premio se le devuelven, y queda la nota «Apartado vencido…» en el
pedido. El último día todavía vale: aparta el 9 y la fecha es el 16, se anula en la madrugada del 17. **Nunca** se anula
solo lo que ya tiene factura publicada, pago hecho o autorizado, o entrega hecha. Una vendedora puede **mover la fecha**
(dar más días) o **borrarla** (la venta ya es firme) en el mismo pedido.

**Avisos.** El sistema **no** le escribe al cliente. Cuando faltan 2 días o menos (`DIAS_DE_AVISO`) la vendedora del
pedido recibe una actividad «Apartado por vencer: avisa al cliente» con el nombre, el teléfono y la fecha; el aviso al
cliente lo manda ella por WhatsApp. Sale una sola vez por fecha de vencimiento (si la marca como hecha no vuelve a salir;
si mueve la fecha, el aviso viejo se quita y llega otro a su hora). Un pedido sin vendedora no genera actividad, pero
aparece igual en la lista.

**La lista.** *Ventas › Hoy › Apartados por vencer* (`/odoo/apartados`): del que vence primero al que vence al final, en
rojo los que vencen hoy o mañana; filtros «Vencen en 2 días o menos», «De la tienda web», «Hechos a mano», «Mis
apartados».

Pendiente (no construido): el botón «Apartar» del cliente en la ficha del producto con abonos (porcentaje mínimo, plazo y
qué pasa con los abonos si vence: lo define la dueña con el abogado; `docs/auditoria/ronda5/pagos-y-apartados.md`).
