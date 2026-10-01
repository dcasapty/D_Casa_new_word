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
| Respaldos en R2 | $0 mientras todo quepa en los 10 GB gratis (hoy la base pesa unos cientos de MB) |
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

**No** poner ninguna regla sobre `pgbackrest/`: pgBackRest borra lo suyo, y borrar por fuera rompe la
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
