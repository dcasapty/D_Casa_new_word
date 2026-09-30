# cf-costos (ronda 2): qué puede hospedar Cloudflare de verdad y cuánto cuesta

Fecha de consulta de todas las fuentes: **2026-09-30**. Agente: `cf-costos`. Solo lectura sobre `addons/`, `edge/`, `docker/`, `.github/`.

## 0. Aviso de método (leer primero)

- `WebFetch` está **bloqueado** por el proxy para `developers.cloudflare.com`, `workers.cloudflare.com`, `hetzner.com` y `bex.co`. No pude abrir ninguna página de precios directamente.
- Todas las cifras salen de **resultados de `WebSearch`** (resúmenes del buscador de páginas oficiales y de terceros). Donde el resultado citaba una página oficial (p. ej. `developers.cloudflare.com/containers/...`), lo marco **[oficial vía buscador]**; donde es blog o agregador, **[tercero]**.
- Ninguna cifra de esta página viene de memoria. Lo que no pude respaldar está en la sección 8 como `(NO VERIFICADO)`. Las cuentas son aritmética propia sobre esas cifras, reproducible (sección 4).
- Conclusión de método: antes de comprometer dinero, el dueño (o `infra` con el MCP de Cloudflare) debe abrir las páginas de la sección 7 y confirmar las tarifas.

## 1. Resumen ejecutivo

1. **Zero Trust / Tunnel no soluciona el problema de la base de datos.** Son una capa de acceso y conectividad. No alojan PostgreSQL ni ejecutan Odoo. Sí resuelven: exponer un servidor propio sin IP pública ni puertos abiertos (Tunnel, gratis), y poner un inicio de sesión previo (Access, gratis hasta 50 usuarios) delante del panel de administración. Detalle en la sección 2.
2. **Cloudflare no tiene PostgreSQL propio.** D1 y Durable Objects son SQLite (Odoo no corre sobre ellos). Hyperdrive solo hace pooling/caché hacia un Postgres externo y, además, el pooling en modo transacción rompe el bus `LISTEN/NOTIFY` de Odoo. Workers VPC/Tunnel solo conecta un Worker a un servidor privado que tú ya tienes.
3. **Postgres dentro de un Cloudflare Container es técnicamente posible pero inseguro para datos contables.** Todo el disco del contenedor es efímero: al dormir, reiniciar, desplegar o mover de host, el disco vuelve a la imagen. Los snapshots existen solo en beta, con limitaciones (sección 3.2). Habría que construir uno mismo un servicio de base de datos con WAL a R2. No lo recomiendo.
4. **Costo real del contenedor de Odoo** (mi cuenta, sección 4): `standard-1` 24/7 ≈ $29/mes, `standard-2` 24/7 ≈ $45,5/mes, más $5 del plan. Confirma la estimación de `infra` (I-01). El presupuesto «$5 + $1 + R2» **no alcanza** para Odoo en Containers ni, con Neon, para la base.
5. **La opción más barata que sigue siendo segura es un VPS único** (Odoo + PostgreSQL locales, `docker compose` ya existente en el repo) **con Cloudflare Tunnel + Access + Worker/CDN adelante y respaldos a R2 con WAL (PITR)**. Costo estimado **≈ €10/mes (≈ $12) de VPS con copia de imagen + $0-5 del Worker + R2 ≈ $0**, o sea **$12-17/mes**, entre 2 y 4 veces menos que la opción Cloudflare pura. Recomendación detallada en la sección 6.
6. **Riesgo de precios**: Hetzner subió precios el 1 de abril y el 15 de junio de 2026; Oracle recortó su nivel gratis a la mitad en 2026; CockroachDB cerró su plan gratis el 2026-09-15; Xata ya no tiene plan gratis. Los precios de esta página envejecen rápido: revalidar al contratar.
7. **Incidente relevante (septiembre 2026)**: Cloudflare corrigió un fallo de Containers que dejaba legibles datos residuales de disco de otros clientes (sección 3.3). Es un argumento adicional contra guardar la base contable en un disco de Container.

## 2. ¿Zero Trust de Cloudflare ya soluciona ese problema?

**No. Precisión:** Zero Trust (Access, Gateway, Tunnel/`cloudflared`) controla **quién llega a qué** y **cómo se conecta** un servidor a Cloudflare. No es un lugar donde vive una base de datos.

| Pieza | Qué es | Qué resuelve para D'CASA | Qué NO resuelve |
|---|---|---|---|
| **Cloudflare Tunnel** (`cloudflared`) | Conector **de salida** desde tu servidor a Cloudflare. Gratis, sin medir ancho de banda ni número de túneles [tercero: bex.co 2026-07-28, recca0120 2026-04-14] | Publicar Odoo desde un VPS (o desde casa) **sin IP pública y sin puertos abiertos**; el dominio `dcasapty.com` apunta al túnel. El repo ya lo trae: `docker compose --profile tunnel` (`docs/DESPLIEGUE.md:104-105`). | No aloja Postgres, no hace respaldos, no da cómputo. |
| **Cloudflare Access** | Inicio de sesión (correo con PIN de un uso, Google, etc.) **antes** de que la petición llegue a Odoo. Gratis hasta **50 usuarios**; después ~$7/usuario/mes [tercero: costbench, controld, zerotrustcost, consultados 2026-09-30] | Proteger el panel (`/odoo`, `/web/database`, etc.) con una segunda puerta. Cortaría fuerza bruta y el gestor de bases expuesto. | No reemplaza la autenticación de Odoo ni los permisos por rol. Ojo: **si se protege `/web/login`, los clientes de la tienda con cuenta (registro `b2c`, ver bitácora seguridad) quedarían bloqueados**; y `/brian/mcp`, `/brian/telegram/*` y `/socios` necesitan política *bypass* o tokens de servicio. Decisión de diseño pendiente (no probé configuración real). |
| **Gateway / WARP** | Filtrado DNS/web de los dispositivos del equipo | Irrelevante para hospedar. | - |
| **Workers VPC / Tunnel + Hyperdrive** | Un Worker alcanza un servicio privado (por ejemplo un Postgres en tu VPC) a través de un túnel | Permitiría a un **Worker** consultar un Postgres propio sin exponerlo. | No aplica a Odoo, que es un proceso Python con `psycopg2`, no un Worker. Detalles de Workers VPC: `(NO VERIFICADO)`. |

Respuesta corta para el dueño: *Zero Trust protege y conecta; para que los datos vivan en algún lado sigue haciendo falta un PostgreSQL real (en un VPS propio o administrado).* Con Tunnel + Access, el VPS puede ser barato y estar cerrado al internet.

## 3. Cloudflare Containers y las alternativas de base dentro de Cloudflare

### 3.1 Containers: tarifas, tipos y límites

Fuente principal: `https://developers.cloudflare.com/containers/pricing/` **[oficial vía buscador, no abierta]**; confirmada en `https://developers.cloudflare.com/changelog/post/2025-11-21-new-cpu-pricing/` (aparece en resultados) y blogs de terceros (bex.co 2026-07/08).

| Concepto | Valor | Nota |
|---|---|---|
| Plan base | **$5/mes** (Workers Paid) | Obligatorio para Containers |
| Memoria | **$0,0000025 por GiB-segundo**; incluido **25 GiB-hora/mes** | Se factura la memoria **aprovisionada** del tipo elegido |
| CPU | **$0,000020 por vCPU-segundo**; incluido **375 vCPU-minuto/mes** | Se factura solo el uso **activo** de CPU |
| Disco | **$0,00000007 por GB-segundo**; incluido **200 GB-hora/mes** | Aprovisionado |
| Granularidad | **cada 10 ms** mientras el contenedor corre | Dormido no factura cómputo |
| `lite` | 1/16 vCPU, 256 MiB, 2 GB | |
| `basic` | 1/4 vCPU, 1 GiB, 4 GB | |
| `standard-1` | 1/2 vCPU, 4 GiB, 8 GB | |
| `standard-2` | 1 vCPU, 6 GiB, 12 GB | el actual en `edge/wrangler.jsonc:15` |
| `standard-3` | 2 vCPU, 8 GiB, 16 GB | |
| `standard-4` | 4 vCPU, 12 GiB, 20 GB | |
| Tipo personalizado | disco máximo 20 GB; tamaño de imagen = espacio de disco de la instancia [tercero: resumen de buscador] | |
| Concurrencia por cuenta | memoria 6 TiB, 1.500 vCPU, 30 TB disco (ampliado 15x) [tercero: post en X de Ashley Peacock citando el changelog] | Irrelevante para una instancia |
| Disco | **Todo efímero**: al dormir, la siguiente vez arranca con disco «fresco» de la imagen [oficial vía buscador: `.../containers/platform-details/architecture/`, `.../containers/guides/snapshots/`] | Clave para Postgres |
| Apagado | `SIGTERM`, espera hasta **15 min**, luego `SIGKILL`; también antes de mover el trabajo de un host [oficial vía buscador: `.../containers/faq/`, `.../platform-details/rollouts/`] | Hay despliegue gradual 10 % / 90 % |
| `sleepAfter` | el contenedor duerme tras ese tiempo sin actividad (p. ej. `"10m"`) | En el repo: `"30m"` + cron `*/10` = nunca duerme (`infra` I-01) |
| Ubicación | Sin lista de regiones: el Durable Object se ubica cerca de la primera petición y el contenedor en «la ubicación más cercana con la imagen» [oficial/tercero vía buscador] | Elegir región: `(NO VERIFICADO)` |
| Arranque en frío | Discrepancia: **2-3 s** (devclass, julio 2025, beta) vs **180-320 ms** (digitalapplied, sin fuente primaria) vs política nueva `durable_object` «6 veces más rápida» (blog de Cloudflare, 2026). Para Odoo manda el arranque de Odoo (decenas de segundos, no medido). | Medir |

Argumento de terceros: bex.co (2026-08-06) titula que los Containers «facturan 5-10 veces más que un VPS siempre encendido» para un servicio de larga duración. Es una opinión de blog; mi cuenta de la sección 4 lo respalda (≈ 4-5x frente a un VPS de €10).

### 3.2 Persistencia: snapshots (beta)

- Existen `snapshotContainer()`: guardan el **sistema de archivos completo**, no la memoria ni los procesos. Máximo **20 GB**, retención **30 días** desde la creación o la última restauración, **atados a la versión de la imagen** (no portables a otra imagen), y solo con la política de programación `durable_object` [oficial vía buscador: `.../containers/guides/snapshots/`].
- Se guardan en R2. Implicaciones para PostgreSQL: un snapshot de un directorio de datos **en marcha** no es consistente salvo que se detenga o se ponga en modo respaldo; y como cada despliegue cambia la imagen, **cada despliegue invalida los snapshots**. Volúmenes persistentes: «explorados pero no para el futuro cercano» (terceros: sliplane, devclass). Alternativa que mencionan: FUSE contra R2 (no probado, rendimiento para Postgres: `(NO VERIFICADO)`).
- Conclusión: hoy no hay disco persistente de verdad en Containers.

### 3.3 Seguridad de la plataforma (septiembre 2026)

Cloudflare corrigió (limpieza terminada el 19-sep, divulgado el 24-sep) un fallo de `dm-thin` que permitía a un contenedor leer bloques de disco residuales de otro cliente; en pruebas hubo datos residuales en 18 de 24 colocaciones, y se recuperaron incluso bases SQLite completas. Cloudflare dice no tener evidencia de explotación [tercero: The Hacker News `https://thehackernews.com/2026/09/cloudflare-fixes-flaw-that-let-one.html`, cyberkendra, gbhackers; 2026-09-30]. Corregido, pero es el tipo de riesgo que no se asume con una base contable si hay alternativa.

### 3.4 ¿Puede PostgreSQL vivir dentro de Cloudflare? Evaluación honesta

| Opción | ¿Sirve para Odoo? | Veredicto |
|---|---|---|
| **Postgres en un Container + respaldo a R2** | Técnicamente sí (Odoo + PG en una imagen, o PG en un segundo Container). Persistencia: **ninguna** salvo lo que envíes a R2. Con WAL-G/pgBackRest archivando WAL a R2 con `archive_timeout` de 60 s, el RPO sería de ~1-5 min si el contenedor muere limpio; con `SIGKILL`/caída de host se pierde lo no archivado; y **cada arranque** exige restaurar base + repetir WAL (minutos-horas según tamaño) antes de que Odoo sirva. Dormir = apagar la base. Además de 8-12 GB de disco de la instancia compartidos con la imagen. | **No recomendado para datos contables.** Es construir un DBaaS casero sobre una plataforma sin disco persistente. Riesgo alto, costo alto (sección 4). |
| **Hyperdrive** | Es pooling/caché **hacia un Postgres externo**. Incluido en Workers Paid sin cargo adicional ni salida; plan gratis 100.000 consultas/día; ~100 conexiones por configuración en Paid [tercero: cipher.co.th, flarecalc, resumen del buscador de `.../hyperdrive/platform/pricing`]. Se consume desde un **Worker**; que un Container Odoo con `psycopg2` lo use: `(NO VERIFICADO)`. El pooling transaccional rompe `LISTEN/NOTIFY` (bitácora `infra` ya lo estableció para el pooler de Neon). | No aloja nada; no aplica a Odoo. |
| **D1** | SQLite administrado; tope **10 GB por base** en Paid, sin tipos enum/array/jsonb/uuid, no se puede importar un volcado de Postgres directamente [tercero: freetier.co, cipher.co.th, inventivehq]. Precio Paid: $0,001/millón de filas leídas, $1,00/millón escritas, $0,75/GB-mes. | **No sirve**: Odoo exige PostgreSQL. |
| **Durable Objects con SQLite** | Almacenamiento por objeto para aplicaciones escritas para Workers. | No sirve para Odoo. |
| **Workers VPC / Tunnel** | Conecta un Worker con un servidor privado propio. | Útil solo si el Postgres vive en tu servidor y lo consumen Workers. No aplica a Odoo. |
| **R2** (respaldos y adjuntos) | Sí. **Lo correcto para respaldos y para `up media`.** | Ver precios abajo. |

**R2** (consistente en 5+ fuentes; página oficial `https://developers.cloudflare.com/r2/pricing/` no abierta, el buscador confirmó cifras iguales): almacenamiento estándar **$0,015/GB-mes**, acceso infrecuente $0,01/GB-mes, operaciones Clase A **$4,50/millón**, Clase B **$0,36/millón**, **salida gratis**; nivel gratis 10 GB-mes, 1 M Clase A, 10 M Clase B al mes [tercero: filebase, vantage.sh, pump.co, themedev; cloudflare.com/products/r2]. Un respaldo diario de ~0,5 GB comprimido con retención 7 diarios + 4 semanales + 12 mensuales (23 copias ≈ 11,5 GB) ≈ 1,5 GB sobre la capa gratis ≈ **$0,02/mes**. Archivar WAL cada minuto ≈ 43.200 operaciones Clase A/mes: dentro del nivel gratis.

## 4. Cuentas paso a paso (mes de 30 días = 720 h = 2.592.000 s)

Fórmulas: memoria = (GiB × segundos − 90.000 GiB-s incluidos) × $2,5e-6; disco = (GB × segundos − 720.000 GB-s incluidos) × $7e-8; CPU = (vCPU × uso_medio × segundos − 22.500 vCPU-s incluidos) × $2e-5. Uso medio de CPU supuesto **10 %** (supuesto mío, sin medir; revisar con datos reales). El cálculo lo verifiqué con un script.

### 4.1 Contenedor de Odoo (sin base), por escenario

| Tipo | Horas/mes | Memoria | Disco | CPU | **Contenedor** | + plan $5 |
|---|---|---|---|---|---|---|
| `standard-2` 24/7 (hoy) | 720 | (6×2.592.000 − 90.000)=15.462.000 × 2,5e-6 = **$38,66** | (12×2.592.000 − 720.000)=30.384.000 × 7e-8 = **$2,13** | (0,1×2.592.000 − 22.500)=236.700 × 2e-5 = **$4,73** | **$45,52** | **$50,52** |
| `standard-1` 24/7 | 720 | (4×2.592.000 − 90.000)=10.278.000 × 2,5e-6 = $25,70 | 20.016.000 × 7e-8 = $1,40 | (0,05×2.592.000 − 22.500)=107.100 × 2e-5 = $2,14 | **$29,24** | **$34,24** |
| `standard-2`, 12 h × 30 d | 360 | $19,21 | $1,04 | $2,14 | **$22,40** | **$27,40** |
| `standard-1`, 12 h × 30 d | 360 | $12,74 | $0,68 | $0,85 | **$14,26** | **$19,26** |
| `standard-1`, 12 h × 22 días hábiles | 264 | $9,28 | $0,48 | $0,50 | **$10,26** | **$15,26** |
| `basic` 24/7 (1 GiB, probablemente corto para Odoo con 8 módulos: medir RSS) | 720 | $6,26 | $0,68 | $0,85 | **$7,78** | **$12,78** |

Notas: (a) «12 h/día» exige que el contenedor **duerma de verdad**: hay que quitar el cron `*/10` fuera de horario (`edge/wrangler.jsonc:25`, ya señalado por `infra`) y los crons de Odoo (puntos de socios cada hora, correo) no corren de noche. (b) Las solicitudes del Worker y del Durable Object se consideran marginales a este volumen; las cuotas incluidas de Workers Paid (solicitudes, CPU) `(NO VERIFICADO)` en esta ronda. (c) Con `workers > 0` en Odoo (multiproceso), el uso de memoria sube (cada worker carga el registro; regla práctica: +0,3-0,5 GiB por worker, **estimación mía sin fuente**) y el bus/WebSocket pasa a otro puerto (`gevent_port`), que Containers (puerto por defecto único) complica; por eso `workers = 0` (decisión documentada en `entrypoint.sh:42`) es coherente con Containers. Con `workers > 0` haría falta `standard-2` como mínimo: escenario 24/7 ≈ $50,5; en horario 12 h/día ≈ $27,4 (memoria dominante). Soporte de 2 puertos: `(NO VERIFICADO)`.

### 4.2 Arquitectura (A): todo en Containers con Postgres propio

- **A1**: un solo contenedor (Odoo + PostgreSQL con `supervisord`) en `standard-2` 24/7: **$50,52** + R2 ≈ $0,1 = **≈ $51/mes**. `standard-1` (4 GiB, 8 GB de disco compartidos con la imagen y la base): **≈ $34,3/mes**, con poco margen de disco.
- **A2**: dos contenedores (Odoo `standard-1` + Postgres `standard-1`) 24/7: 2 × $29,24 + $5 = **$63,48/mes**.
- Con horario de 12 h (22 días hábiles) y A1 `standard-2`: memoria 6 GiB × 950.400 s = 5.702.400 GiB-s − 90.000 = 5.612.400 × 2,5e-6 = $14,03; disco $0,75; CPU $1,45 → $16,23 + $5 = **$21,23**. Pero cada noche Postgres **se apaga y su disco se pierde**: hay que restaurar desde R2 cada mañana (RPO = último WAL archivado antes del apagado; RTO diario de minutos). Es viable solo si se acepta ese ritual; **no lo recomiendo** para contabilidad.

### 4.3 Neon (referencia; el dueño lo descartó)

Launch: **$0,106 por CU-hora**, almacenamiento **$0,35/GB-mes** [tercero: srvrlss, swyftstack, buildmvpfast; consultados 2026-09-30]; plan gratis 0,5 GB y 100 CU-h por proyecto. Con Odoo 24/7 (cron cada ~60 s + conexión del bus; Neon recomienda desactivar el autosuspend si hay `LISTEN/NOTIFY`, fuente: neon.com/guides/pub-sub-listen-notify) el cómputo nunca se suspende: 0,25 CU × 720 h × $0,106 = **$19,08** + 2 GB × $0,35 = $0,70 ≈ **$19,8/mes**. El plan gratis de 100 CU-h (= 400 h a 0,25 CU) no alcanza para 720 h. Confirma lo dicho por `infra`.

### 4.4 Arquitectura (B): VPS único

- Hetzner **CX33** (tras el ajuste del 15-jun-2026): **€8,49/mes** según `docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/` **[oficial vía buscador]** (CX23 €5,49; CX43 €15,99). **Discrepancia**: blogs (bitdoze.com, northflank.com) dan CX23 €5,99. Se usa la cifra oficial; revalidar al contratar. Copias de imagen automáticas («Backups»): **20 % del precio del servidor**, hasta 7 [tercero: betterstack/hetsnap]: +€1,70. Snapshots €0,0143/GB-mes. Precios sin IVA. **Total VPS ≈ €10,19/mes ≈ $12** (tipo de cambio no consultado; uso 1 € ≈ 1,17 $ como aproximación **mía**, sin fuente).
- Ubicación: los CX son solo de la UE (Alemania/Finlandia). Hetzner en EE. UU. (Ashburn/Hillsboro) cuesta **más**: una fuente da CPX21 (3 vCPU, 4 GB, 1 TB de tráfico) a **$37,49** y otra «planes de EE. UU. desde $20,49» [terceros, discrepan; bestusavps.com, agentdeals.dev]. La latencia usuario-Panamá↔UE no está medida (`NO VERIFICADO`); como la base es local, solo hay **un** viaje de red por página (usuario↔servidor), no decenas (Odoo↔Neon).
- Alternativas de VPS en América: DigitalOcean Droplet 2 vCPU/4 GB **$24**; Vultr Regular 2 vCPU/4 GB **$20** (alto rendimiento $24) [terceros: fluence.ai, betterstack, costbench]. Contabo Cloud VPS 10 (4 vCPU, 8 GB, 75 GB NVMe): **€4,50-5,36 / $4,95-6,6** según fuente (discrepan; terceros: whtop, vpsbenchmarks, cheapvps), 32 TB de tráfico; fama de rendimiento variable `(NO VERIFICADO)`.
- Cloudflare: Tunnel gratis, Access gratis (≤ 50 usuarios), DNS/CDN proxied. Worker opcional ($5 del plan Workers Paid, ya previsto por el dueño) para conservar `edge/src/routing.ts` (bloqueos, cabeceras, caché).
- R2: ≈ $0,02-0,2.
- **Total B: ≈ $12 (solo VPS + Tunnel + Access + R2) a ≈ $17 (con Worker)**. Con DigitalOcean/Vultr en EE. UU. en lugar de Hetzner: $20-24 + $0-5 = **$20-29**.

### 4.5 Comparativa

| | A1 todo en Containers | A2 2 contenedores | B VPS + Tunnel + R2 | C Container Odoo + Postgres en VPS | D1 Container + Neon (antes) |
|---|---|---|---|---|---|
| Costo mensual | $34-51 (24/7) / $21 en horario | $63,5 | **$12-17** ($20-29 si VPS en EE. UU.) | $29-46 (contenedor) + $5 + VPS ≈ $44-56 | $34-70 (infra.md §4.3) |
| Base persistente | No (disco efímero) | No | **Sí (disco del VPS)** | Sí (VPS) | Sí (Neon) |
| PITR | Hay que montarlo (WAL a R2) | Ídem | **WAL a R2 (pgBackRest/WAL-G)** | Ídem | Neon (retención por plan, `NO VERIFICADO`) |
| Latencia Odoo↔BD | ~0 (mismo host) o red interna | red interna | **0** | **Alta**: Container en ubicación variable ↔ VPS; decenas de consultas por página | Alta (medir) |
| Mantenimiento | Alto (DBaaS casero) | Alto | **Medio** (parches del SO, disco, respaldos) | Medio-alto (dos plataformas) | Bajo |
| Sesiones/carritos | Se pierden al dormir | Ídem | **Persisten** (disco) | Se pierden (Container) | Se pierden |
| Si se cae | Reinicio = restauración desde R2 | Ídem | VPS caído = sitio caído hasta reponer; restaurar en otro VPS desde R2 | Dos puntos de falla | Contenedor o Neon |

La opción C es estrictamente peor que B (paga el Container y además mezcla latencias): **descartada**.

## 5. Alternativas de base de datos/cómputo (Postgres administrado o VPS)

Consultas a 2026-09-30, fuentes de terceros salvo indicación. Patrón de Odoo: **1 conexión de bus con `LISTEN/NOTIFY`**, hilo de cron que despierta cada ~60 s (dato de la tarea; no lo verifiqué en `vendor/odoo`), `db_maxconn = 16` en el repo. Por tanto: **autosuspend/scale-to-zero inútil** (nunca hay inactividad), **pooler en modo transacción inadmisible**, y se necesitan >= 20 conexiones.

| Proveedor | Precio | Límites relevantes | ¿Tolera Odoo? | Respaldo/PITR |
|---|---|---|---|---|
| **Supabase** Free | $0 | 500 MB BD, se **pausa tras 1 semana de inactividad** (Odoo nunca está inactivo, pero 500 MB no alcanza con adjuntos en BD) | Justo: tamaño | Sin PITR |
| **Supabase** Pro | $25/mes por proyecto (cómputo Micro incluido) | PITR exige cómputo >= Small | Sí, conexión directa | Copias diarias 7 días; **PITR desde $100/mes (7 días)** → total >= $135. Caro. |
| **Neon** Launch | $0,106/CU-h + $0,35/GB | autosuspend a desactivar por `LISTEN` | Sí, ≈ $20/mes 24/7 | Sí (retención a verificar) |
| **Aiven** Free | $0 | 1 CPU, 1 GB RAM, **1 GB disco, `max_connections` = 20**, sin tarjeta | Muy justo (20 conexiones vs 16 de Odoo + cron + bus) y 1 GB de disco | Copias incluidas |
| **Xata** | Sin plan gratis; ~$0,012/h micro (≈ $8,6/mes) + $0,28/GB-mes | Crédito de $100 por 14 días | Posible | `NO VERIFICADO` |
| **CockroachDB** | Plan gratis Basic **cerrado a nuevos el 2026-09-15**; prueba 30 días con $400 | No es PostgreSQL completo | **No** (Odoo usa características de PG; además cerrado) | - |
| **DigitalOcean** PG administrado | desde **$15,15/mes** (1 GiB, nodo único); 4 GiB **$60,90** | 1 GiB es poco para PG con Odoo | Sí | copias/PITR: `NO VERIFICADO` |
| **Fly.io** | VM shared-cpu-1x 1 GB ≈ $5,70; volumen $0,15/GB-mes; snapshots $0,08/GB-mes (10 GB gratis); **Managed Postgres Basic $38/mes** (1 GB) | Facturación por medidores; subió líneas en 2026 | Sí, caro el administrado | snapshots de volumen |
| **Railway** | Hobby $5 + uso: $20/vCPU-mes, $10/GB-mes | Odoo 2 GB+0,5 vCPU ≈ $30 + PG 1 GB+0,25 vCPU ≈ $15 + $5 ≈ **$50** (cuenta mía) | Sí, caro | copias |
| **Render** PG | Basic-256mb **$6**; gratis **vence a los 30 días** | 256 MB RAM, ~97 conexiones | No (RAM) | - |
| **Oracle Cloud Always Free** | $0 | **Recortado en 2026**: de 4 OCPU/24 GB a **2 OCPU/12 GB** (InfoQ 2026-07, linuxiac); instancias ociosas se **reclaman** (p95 CPU/red/memoria < 20 % durante 7 días en A1); cuentas de pago podrían conservar 4/24 según soporte (foros; discrepa) | Alcanza en recursos; **no** en confianza para contabilidad | Sin respaldo propio |
| **Hetzner Cloud** | CX23 €5,49 (2 vCPU/4 GB) / CX33 €8,49 (4 vCPU/8 GB) / CX43 €15,99 | Solo UE (CX); sube precios con frecuencia | **Sí** (PG local) | Backups 20 %; WAL a R2 |
| **Contabo** | ~€4,50-5,36 (4 vCPU/8 GB) | Reputación de rendimiento irregular `(NO VERIFICADO)` | Sí | propio |
| **DigitalOcean / Vultr** | $24 / $20 (2 vCPU/4 GB) | Regiones en EE. UU. | Sí | backups de pago `NO VERIFICADO` |

Conclusión del bloque: **no existe un Postgres administrado con PITR por debajo de ~$20/mes que sirva para Odoo 24/7** (Neon ≈ $20 es el más barato con PITR real; Supabase con PITR ≥ $135). La base en el mismo VPS con WAL a R2 es **5-10 veces más barata** y da PITR equivalente, a cambio de operarla tú.

## 6. Recomendación final con número

### Opción recomendada: B, VPS único + Tunnel + Access + Worker + R2

**Costo objetivo: ≈ $12/mes (VPS Hetzner CX33 + copias de imagen, Tunnel, Access, R2) a ≈ $17/mes si se conserva el Worker de $5.** Es la más barata que cumple: respaldos verificables y PITR.

Piezas mínimas y qué las hace seguras para datos contables:
1. **PostgreSQL 16 local** con `archive_mode=on`, `archive_timeout=60` y **pgBackRest o WAL-G → R2** (cifrado con `age`/clave de repositorio): PITR con RPO ≈ 1-5 min. Base completa diaria o semanal; retención 7 + 4 + 12.
2. **Copia de imagen del VPS** (Hetzner Backups, +20 %) como segundo paño, no como respaldo principal.
3. **Prueba de restauración automática** mensual (workflow de GitHub Actions que baja el respaldo de R2, restaura en el servicio `postgres:16` del CI y arranca Odoo contra esa copia) con alarma si falla. Sin esta prueba el respaldo no cuenta como «verificable».
4. **Tunnel + Access**: el VPS con todos los puertos entrantes cerrados (solo SSH por llave o también por Tunnel); Access delante del panel con política *bypass* para `/brian/*`, `/socios`, tienda y webhooks (diseñar y probar; ver sección 2).
5. Pimienta del PIN (`DCASA_PIN_PEPPER`) copiada fuera del VPS y del Worker (hallazgo `infra` I-14).

**Qué habría que cambiar en el repo (propuesta; los agentes no lo aplican):**
- `docker/entrypoint.sh`: sin cambio funcional (`DB_HOST` local, `DB_SSLMODE=disable`/`prefer`); reforzar `sql()` (I-06) y mover la migración fuera del arranque (I-02): con VPS es aún más fácil, `docker compose run --rm odoo -u ...` antes de `up -d`, **después** de un `pg_dump`/punto de restauración. Quitar la regla «adjuntos en BD por falta de disco» (`CLAUDE.md`, convenciones) solo si se decide usar filestore; mantener en BD simplifica el respaldo (un solo artefacto) y es razonable.
- `docker-compose.yml`: agregar servicio de respaldo (pgBackRest/WAL-G) y `cloudflared` (ya existe el perfil `tunnel`, `docs/DESPLIEGUE.md:104-105`); volumen con nombre para `pgdata` y `odoo-data` (sesiones persisten).
- `edge/`: si se mantiene el Worker, sustituir `OdooContainer`/`migrations` por `fetch` al hostname del túnel (origen); se conservan `routing.ts` y `handler.ts` (bloqueos, cabeceras, caché). Quitar `containers` y `durable_objects` de `edge/wrangler.jsonc` y el cron.
- `.github/workflows/ci.yml`: el job `deploy` (hoy `wrangler deploy` con imagen) pasa a «construir imagen → publicar en registro → SSH restringido `docker compose pull && up -d` tras la migración». Nuevo workflow programado de prueba de restauración. `wrangler deploy` del Worker sigue (solo código).
- `docs/DESPLIEGUE.md`, `docs/ARQUITECTURA.md`, `docs/PLAN.md` Fase 3: reescribir; corregir la contradicción del «contenedor duerme».

### Plan B (si el dueño no quiere administrar un servidor)
- **B1**: **Container `standard-1` en horario laboral + Neon Launch** (`infra` escenario C): ≈ $14,3 + $5 + Neon (~$10-20) ≈ **$30-40/mes**, sin administrar SO, con PITR de Neon + `pg_dump` diario a R2 (I-03). Persisten las incógnitas de latencia (I-05).
- **B2**: mismo diseño B en otro proveedor con región americana (DigitalOcean/Vultr ≈ $20-24 + Worker opcional) si la latencia a Europa resulta mala; **los respaldos en R2 hacen la mudanza una restauración**.
- No recomendados: A1/A2 (datos en disco efímero), Supabase con PITR (≥ $135), Oracle gratis (recorte y reclamación de instancias), CockroachDB (incompatible y plan cerrado).

### Qué medir antes de comprometerse (todo a bajo costo)
1. **Latencia usuario↔VPS**: alquilar una hora de CX23 (o DigitalOcean/Vultr en EE. UU.) y medir TTFB de `/`, `/shop`, `/web/login` desde Panamá y con el equipo de la tienda. Decide UE vs EE. UU.
2. **RSS real de Odoo** (8 módulos + catálogo cargado, con y sin `workers`) en una imagen de prueba: decide 4 GB vs 8 GB de RAM y si `basic`/`standard-1` de Containers alcanzaría en el plan B1.
3. **Tamaño real de la base** y de `pg_dump` comprimido: fija costo de R2 y tiempo de restauración.
4. **Tiempo de restauración de extremo a extremo** (R2 → PITR → Odoo arriba): debe caber en el RTO objetivo de 2 h (`infra.md` I-03).
5. **Uso medio de CPU** (supuse 10 %): reemplazar en la cuenta de la sección 4.
6. **Política de Access** frente a tienda, `/socios`, `/brian/*`: probar que no bloquea clientes ni webhooks.
7. Releer las páginas de precios de la sección 7 en vivo (yo no pude abrirlas).

### Costo de Brian (APIs de IA), línea aparte
No hay datos de volumen de uso de la tienda, así que **solo doy el precio unitario y un ejemplo ilustrativo con supuestos míos**. Tarifas de la API de Anthropic (tabla «Current Models», cacheada 2026-09-25, del skill `claude-api` de esta sesión; no abrí `claude.com/pricing`): Claude Sonnet 5.5 **$2 / $10 por millón de tokens** (entrada/salida; lecturas de caché $0,20), Claude Opus 5.5 **$4 / $20**, Claude Haiku 4.5 **$1 / $5**. Ejemplo: una interacción de Brian con 6.000 tokens de entrada y 500 de salida en Sonnet 5.5 = 6.000×$2e-6 + 500×$10e-6 = **$0,017**; con 5.000 tokens servidos de caché ≈ **$0,008**. A 1.000 interacciones/mes: **≈ $8-17/mes**; a 5.000: ≈ $40-85. Con Haiku 4.5 sin caché: $0,0085 por interacción. La lectura de Excel con imágenes (visión) añade tokens de imagen: `(NO VERIFICADO)`, lo cubre `brian-modelos`/`brian-excel`. Las cifras de OpenAI y Meta no se consultaron aquí.

## 7. Fuentes (URL, fecha de consulta 2026-09-30)

Oficiales (aparecieron en `WebSearch`; contenido **no abierto** por bloqueo de proxy, salvo lo que muestra el resumen):
- Cloudflare Containers, precios: https://developers.cloudflare.com/containers/pricing/
- Cloudflare Containers, limits/instance types: https://developers.cloudflare.com/containers/platform/limits/
- Ciclo de vida/arquitectura: https://developers.cloudflare.com/containers/platform-details/architecture/
- Rollouts y SIGTERM: https://developers.cloudflare.com/containers/platform-details/rollouts/ y https://developers.cloudflare.com/containers/faq/
- Snapshots: https://developers.cloudflare.com/containers/guides/snapshots/
- Changelog de nuevos precios de CPU: https://developers.cloudflare.com/changelog/post/2025-11-21-new-cpu-pricing/
- Hyperdrive, precios: https://developers.cloudflare.com/hyperdrive/platform/pricing
- D1, límites: https://developers.cloudflare.com/d1/platform/limits
- R2: https://www.cloudflare.com/products/r2/ y https://developers.cloudflare.com/r2/pricing/ (no abierta)
- Hetzner, ajuste del 15-jun-2026: https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
- Oracle Always Free: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Aiven Free PostgreSQL: https://aiven.io/docs/products/postgresql/concepts/pg-free-tier
- Tarifas de Claude: tabla del skill `claude-api` (cacheada 2026-09-25)

Terceros (usados para cifras o contexto; menor confianza):
- Containers y costos vs VPS: https://bex.co/blog/2026/08/06/cloudflare-containers-pricing-vs-always-on-vps , https://bex.co/blog/2026/08/21/cloudflare-containers-vs-hetzner-fleet-cost-architecture , https://sliplane.io/blog/cloudflare-released-containers-everything-you-need-to-know , https://devclass.com/2025/07/01/cloudflare-container-platform-in-public-preview-with-scale-to-zero-pricing-some-initial-limitations/ , https://x.com/_ashleypeacock/status/2026650757542338994
- Fallo de disco (sept 2026): https://thehackernews.com/2026/09/cloudflare-fixes-flaw-that-let-one.html , https://www.cyberkendra.com/2026/09/cloudflare-containers-cross-tenant-disk-data-flaw.html
- R2: https://filebase.com/blog/cloudflare-r2-pricing-costs-savings-and-alternatives-in-2026/ , https://www.vantage.sh/blog/cloudflare-r2-aws-s3-comparison
- Hyperdrive: https://www.cipher.co.th/en/blogs/cloudflare-hyperdrive-postgres/ , https://flarecalc.com/calculators/hyperdrive/
- D1: https://freetier.co/articles/cloudflare-d1-free-tier-limits-pricing-and-alternatives , https://www.cipher.co.th/en/blogs/cloudflare-d1-vs-postgresql/
- Zero Trust/Tunnel: https://costbench.com/software/business-vpn/cloudflare-zero-trust/free-plan/ , https://controld.com/blog/cloudflare-zero-trust-pricing/ , https://bex.co/blog/2026/07/28/cloudflare-tunnel-free-zero-open-ports-ingress
- Neon: https://swyftstack.com/blog/neon-pricing-explained , https://neon.com/guides/pub-sub-listen-notify
- Supabase: https://www.supabackup.com/blog/supabase-pitr-pricing (PITR) y https://uibakery.io/blog/supabase-pricing
- Hetzner: https://northflank.com/blog/hetzner-cloud-server-price-increases , https://www.bitdoze.com/hetzner-cloud-cost-optimized-plans/ , https://bestusavps.com/reviews/hetzner/ , https://hetsnap.com/blog/hetzner-cloud-backup-vs-snapshot-pricing-comparison
- Oracle recorte: https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/ , https://linuxiac.com/oracle-quietly-cuts-free-tier-ampere-a1-resources-in-half/
- Otros: https://fluence.ai/blog/digitalocean-droplets-vs-fluence/ , https://infratally.com/articles/digitalocean-managed-postgresql-pricing-2026-billing-model/ , https://northflank.com/blog/railway-vs-flyio , https://makerkit.dev/pricing-calculator/railway , https://www.srvrlss.io/provider/render/ , https://layerbase.com/blog/xata-alternatives , https://github.com/robhunter/agentdeals/issues/1933 (CockroachDB) , https://www.vpsbenchmarks.com/hosters/contabo/plans/cloud-vps-10

## 8. Discrepancias entre fuentes y lo NO VERIFICADO

**Discrepancias**
- Hetzner CX23: €5,49 (docs.hetzner.com vía buscador) vs €5,99 (northflank/bitdoze). Preferí la oficial.
- Hetzner EE. UU.: CPX21 $37,49 (agentdeals) vs «planes de EE. UU. desde $20,49» (bestusavps). Sin resolver.
- Contabo Cloud VPS 10: €4,50 / €5,36 / $4,95 / $6,6 según fuente.
- Arranque en frío de Containers: 2-3 s (2025, beta) vs 180-320 ms (terceros) vs «6 veces más rápido» con política `durable_object`. Para Odoo domina el arranque de Odoo, no medido.
- Oracle Always Free: 2 OCPU/12 GB (InfoQ, linuxiac) vs «cuentas de pago conservan 4/24» (reportes de soporte en foros).
- `infra.md` estimaba disco 12 GB = $2,1 y contenedor $45,5: **coincide** con mi cuenta ($2,13; $45,52).

**(NO VERIFICADO)**
1. Cuotas incluidas de Workers Paid (solicitudes, CPU, cron) y si Workers/R2 necesitan Paid para este uso.
2. Regiones elegibles para Containers y `locationHint`; latencia contenedor→Neon.
3. Si un Container puede usar Hyperdrive (y si serviría a Odoo): asumido que no.
4. Workers VPC: precios y límites; Access sobre rutas concretas de Odoo en la práctica (tienda, `/socios`, `/brian/*`).
5. Soporte de un segundo puerto (WebSocket/gevent) en Containers para `workers > 0`.
6. Uso medio de CPU de Odoo (10 % supuesto), RSS real, tamaño de base y de imagen.
7. Memoria adicional por worker de Odoo (+0,3-0,5 GiB, estimación mía).
8. Que el cron de Odoo despierta cada ~60 s (dato de la tarea; no verificado en `vendor/odoo`).
9. PITR y retención de Neon en Launch; copias/PITR de DigitalOcean; retención de Aiven.
10. Latencia Panamá↔Europa y Panamá↔EE. UU. por proveedor; rendimiento real de Contabo.
11. Tipo de cambio €/$ (1,17 es aproximación mía).
12. Precios de tokens de imagen (Excel con imágenes) y de OpenAI/Meta: fuera de alcance de este agente.
13. Si los precios vigentes de Claude en `claude.com/pricing` coinciden con la tabla del skill (cacheada 2026-09-25).
