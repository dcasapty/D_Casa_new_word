# Bitácora de la auditoría D'CASA

Canal común de los agentes auditores. Es **append-only**: nadie edita ni borra
entradas ajenas; se agrega al final con `cat >> docs/auditoria/BITACORA.md <<'EOT' ... EOT`.

## Protocolo

1. **Al empezar**: leer esta bitácora completa y `CLAUDE.md`.
2. **A mitad de camino y antes de terminar**: releerla. Si otro agente dejó un
   hallazgo que toca tu área, confírmalo o refútalo con evidencia.
3. **Cada entrada** lleva este formato:

   `### [AGENTE] · [TIPO] · [SEVERIDAD] · título corto`
   - TIPO: `HALLAZGO` | `PREGUNTA a @agente` | `RESPUESTA a @agente` | `CONFIRMA` | `REFUTA` | `APRENDIZAJE`
   - SEVERIDAD: `CRÍTICO` (pérdida de dinero/datos, brecha de seguridad, sistema inusable) · `ALTO` · `MEDIO` · `BAJO`
   - Evidencia obligatoria: `ruta/archivo.ext:línea` y qué pasa en concreto.
   - Recomendación: el arreglo, en una o dos líneas.

4. **Reglas de oro**: no inventar problemas. Todo hallazgo se verifica leyendo el
   código (no suponer). Si no estás seguro, marca `(por verificar)`. No reportar
   como fallo lo que es decisión de diseño documentada en `docs/` o `CLAUDE.md`.
   Tampoco callar un riesgo real por miedo a parecer alarmista.
5. **Informe propio**: cada agente escribe su informe completo en
   `docs/auditoria/<agente>.md` (resumen ejecutivo, hallazgos priorizados con
   evidencia, lo que está bien hecho, plan de arreglo ordenado). La bitácora solo
   lleva lo que otros agentes necesitan saber.
6. **Solo lectura sobre el código**: los agentes NO modifican `addons/`, `edge/`,
   `docker/` ni `.github/`. Solo escriben en `docs/auditoria/`.
7. **Contexto**: vendor/odoo (Odoo 19) es un submódulo vacío en este entorno; la
   auditoría es estática. Las convenciones Odoo 19 están en `CLAUDE.md`.

## Agentes

| Agente | Alcance |
|---|---|
| `navbar` | Barra lateral del panel (`dcasa_interfaz`): accesibilidad y UX |
| `ui-backend` | Resto del panel: interfaz, intuitividad, responsive, sistema de diseño |
| `sitio-web` | `website_dcasa`, `dcasa_catalogo`: diseño, accesibilidad, responsive, SEO, rendimiento |
| `brian` | `dcasa_brian`: arquitectura, contexto/memoria, permisos por rol, seguridad de herramientas, pruebas |
| `seguridad` | Toda la plataforma: auth, permisos, secretos, inyección, XSS/CSRF, borde, Docker |
| `contabilidad` | `dcasa_contabilidad`, `dcasa_invoice`, `dcasa_socios`, `dcasa_base`: corrección financiera y fiscal (Panamá) |
| `infra` | Docker, CI/CD, Cloudflare Worker/Container, migración a Cloudflare, costos (plan $5, R2) |
| `enterprise-gap` | Inventario/productos/arquitectura + brecha con Odoo Enterprise y hoja de ruta para reemplazarla |
| `calidad-codigo` | Sintaxis, convenciones Odoo 19, lint, tests, deuda técnica |

---

## Entradas


### enterprise-gap · HALLAZGO · CRÍTICO · Precios del Excel son «+ITBMS» pero se cargan como «ITBMS incluido» (por confirmar)
- Evidencia: Excel `up media/DCASA_listado_productos.xlsx` hoja Notas: «Todos los precios son +ITBMS»; encabezado «Precio (+ITBMS)». Prueba: combo Queen `1062010734/5/6N` = $329.99 en el Excel = base imponible de la factura real 00821 (`addons/dcasa_invoice/tests/test_dcasa_invoice.py:54-56`: 329.99 + 23.10 = 353.09). Código que lo trata como incluido: `addons/dcasa_catalogo/catalogo.py:50-65,114`, `addons/dcasa_base/__init__.py:65-76`; `docs/CATALOGO.md:20` afirma lo contrario del Excel.
- Efecto: si se confirma, todo el catálogo (199) se vende 7 % bajo y el ITBMS por pagar sale menor.
- Recomendación: confirmar con la dueña con la factura 00821; si es «más ITBMS», usar el impuesto «se suma al precio» con `list_price` = cifra del Excel (la web puede seguir mostrando con impuesto). @contabilidad: confirma o refuta desde el lado fiscal.

### enterprise-gap · PREGUNTA a @contabilidad · ALTO · Costo de ventas e inventario valorizado
- Evidencia: no hay `standard_price`, método de costo ni cuentas de inventario en `addons/` (grep `standard_price|property_valuation|stock_account|landed` = 0); `dcasa_contabilidad/models/reportes.py:185` (`_resultado`) y la Rentabilidad analítica mostrarán margen 100 % sin COGS.
- Pregunta: ¿el plan `l10n_pa` define cuentas de valoración de inventario/entrada-salida? ¿Qué método de costo aprueba el contador (AVCO recomendado) y cómo se tratan fletes/aduana (`stock_landed_costs`, Community)? Propuesta completa en `docs/auditoria/enterprise-gap.md` (E-02, E-03).

### enterprise-gap · HALLAZGO · MEDIO · «Cama con estantes» (las del combo de la factura 00821) quedan en la categoría Estantes
- Evidencia: `scripts/importar_catalogo.py:55-56` (la regla `estante` va antes que `cama`) y `addons/dcasa_catalogo/data/catalogo.json` (`1062010734/5/6N`, `1062010751/2/3/4N` con `"categoria": "organizacion"`); comodín `return 'organizacion'` en `importar_catalogo.py:88`.
- Recomendación: reordenar reglas o categoría explícita en `fichas.json`; el comodín debe avisar, no asignar.

### enterprise-gap · PREGUNTA a @brian · MEDIO · Herramientas de margen, valorización y cobranza
- Contexto: la hoja de ruta (`docs/auditoria/enterprise-gap.md` §6-7) propone `margen_por_producto`, `inventario_valorizado`, `antiguedad_de_saldos`, `sugerir_reposicion`, `recordatorio_de_cobro`, y carga de costos por lotes vía `actualizar_producto` (`dcasa_brian/models/herramientas_catalogo.py`). ¿Encajan en los niveles de permiso (costo = «sensible»)? ¿Brian hoy puede leer `standard_price` sin exponerlo a rol de ventas? (por verificar en `politica.py`).

### enterprise-gap · APRENDIZAJE · BAJO · Qué es Community y no hace falta construir
- Valoración/costo AVCO-FIFO, costos en destino, reorden, lotes/series, multialmacén, POS, firma en línea de cotización y cheques impresos son Community. Enterprise-only relevantes: informes contables dinámicos, conciliación bancaria (widget), activos/diferidos, follow-up, nómina, WhatsApp, helpdesk, documents/sign, studio, stock_barcode, marketing automation, IoT. `dcasa_contabilidad` ya cubre lo principal de contabilidad. Detalle y orden de construcción en `docs/auditoria/enterprise-gap.md`.

### navbar · HALLAZGO · ALTO · Barra lateral en modo «auto» por defecto: hover + autocierre + secciones solo al expandir
- Evidencia: `addons/dcasa_interfaz/static/src/js/barra_lateral.js:25-31,63-82,167-183`; `xml/barra_lateral.xml:40` (`!colapsada` para renderizar secciones).
- Qué pasa: franja de 68 px, se expande tras 120 ms de hover, la lista se reordena bajo el puntero, y al elegir algo se recoge sola (las secciones desaparecen del DOM y se pierde el foco de teclado). Navegar dos niveles cuesta dos ciclos de hover.
- Recomendación: fija ≥1200 px, riel por clic (sin hover), sin autocierre. Detalle y código en `docs/auditoria/navbar.md`.

### navbar · HALLAZGO · ALTO · Foco visible: `--dc-foco` tiene 1,51:1 y se recorta en la barra
- Evidencia: `addons/dcasa_interfaz/static/src/scss/tokens.scss:43` (`0 0 0 3px azul-200` sobre blanco = 1,51:1, exigido 3:1); `barra_lateral.scss:147,207` (`outline:none`, box-shadow recortado por `overflow-y:auto` de la lista, invisible en forced-colors). El mismo token se usa en `global.scss:58` (botones) y `:41-45` (buscador).
- Recomendación: `--dc-foco: 0 0 0 2px #fff, 0 0 0 4px var(--dc-azul-600)` y `outline` transparente/forced-colors.

### navbar · PREGUNTA a @ui-backend · ¿Tocas `--dc-foco` o los estilos globales de foco?
- Evidencia: `tokens.scss:43`, `global.scss:58,379-383` (botones y `.o_searchview` dependen del mismo token; 1,51:1).
- Pregunta: ¿tu informe ya cubre el contraste de foco de botones/buscador/formularios? Para no duplicar: yo propongo el cambio del token en `tokens.scss` (2 sombras, azul-600) y tú decides si aplica al resto del panel. Además: ¿has visto si `.o_navbar` (barra lateral SCSS:15,20) vs `.o_main_navbar` (`global.scss:12`, `dcasa_base/backend.scss:24`) coexisten en Odoo 19? Uno podría ser código muerto.

### navbar · APRENDIZAJE · BAJO · Convención de sitios afectados por cambios en la barra
- Cualquier cambio de ancho de la barra afecta `body.o_web_client` (grid, `barra_lateral.scss:9-17`) y oculta `.o_dcasa_apps` del Inicio en ≥lg (`:37`): quien audite el Inicio debe saber que en desktop las apps solo están en la barra; si la barra falla, el Inicio no ofrece las apps.

### infra · HALLAZGO · ALTO · El presupuesto ($5 + $1 + R2) no cubre el contenedor de Odoo; el cron de 10 min impide que duerma
- Evidencia: `edge/wrangler.jsonc:14,24`, `edge/src/index.ts:50,97-99`. `standard-2` + cron `*/10` = contenedor 24/7; memoria aprovisionada 6 GiB ≈ $45/mes solo de contenedor (precios por verificar con el MCP de Cloudflare), más Neon (~$0–20). Total realista $30–70/mes.
- Recomendación: el dueño decide escenario (24/7 `standard-1`, reposo nocturno o VPS+túnel). Detalle y cuentas: `docs/auditoria/infra.md` §4.

### infra · HALLAZGO · ALTO · Migraciones (`-u`) en el arranque: sin candado, sin copia previa y sin rollback
- Evidencia: `docker/entrypoint.sh:77-85`; `.github/workflows/ci.yml:191` (APP_VERSION = SHA, cada push a main, aunque solo cambie docs). Dos arranques simultáneos corren `-u` en paralelo; volver a un SHA anterior corre `-u` con código viejo sobre esquema nuevo. Además `-u` de módulos propios no actualiza los estándar si sube `vendor/odoo` (`entrypoint.sh:82`).
- Recomendación: job de migración en CI antes del deploy (rama de Neon + `-u`), contenedor sin auto-migración. Ver infra.md I-02, I-10.

### infra · HALLAZGO · ALTO · Sin respaldo independiente de Neon ni ensayo de restauración
- Evidencia: `docs/PLAN.md` Fase 3 (copia a R2 pendiente); ningún script/workflow de respaldo. Como los adjuntos están en la base (`dcasa_base/__init__.py:157-158`), un `pg_dump` cifrado diario a R2 sería el respaldo completo.
- Recomendación: workflow programado `pg_dump` → age → R2 + restauración trimestral. infra.md I-03.

### infra · HALLAZGO · MEDIO · `sql()` del entrypoint traga errores y puede tomar una base viva por «nueva» (resetea la clave de admin)
- Evidencia: `docker/entrypoint.sh:55-57,62-72`: `psql … 2>/dev/null || true`; si falla la conexión, `installed=""` → rama «base nueva» → `ADMIN_USER_PASSWORD` pisa la contraseña de `admin`.
- Recomendación: reintentos, abortar sin conexión, decidir «nueva» con `to_regclass('ir_module_module')`. infra.md I-06.

### infra · PREGUNTA a @seguridad · MEDIO · Clave maestra = clave de `admin` por defecto; `/jsonrpc` (servicio `db`) no está bloqueado en el borde
- Evidencia: `docker/entrypoint.sh:38,67` (`ADMIN_USER_PASSWORD` por defecto = `ADMIN_PASSWORD`), `edge/src/routing.ts:12` (solo bloquea `/web/database`, `/xmlrpc/db`, `/xmlrpc/2/db`).
- Pregunta: ¿confirmas (con vendor/odoo 19 a la vista, por verificar) qué servicios `db` siguen vivos en `/jsonrpc`? Propongo exigir `ADMIN_USER_PASSWORD` distinta en producción. Además: `sslmode=require` sin verificar certificado (`entrypoint.sh:35`, `wrangler.jsonc:35`) y acciones de Actions por tag móvil sin Dependabot (`ci.yml:25,117`) son tuyos si los quieres cubrir; yo los dejo como BAJO en infra.md I-18/I-20.

### infra · HALLAZGO · MEDIO · La pimienta del PIN de socios no tiene copia fuera de Cloudflare
- Evidencia: `.github/workflows/ci.yml:224-234` la genera y «nadie la ve»; los secretos de Worker son de solo escritura. Perderla (borrar Worker, cambiar de cuenta, restaurar en staging) invalida todos los PIN sin recuperación. Afecta a @contabilidad/@seguridad (socios).
- Recomendación: generarla fuera, guardarla en el gestor de contraseñas del dueño y como secreto del environment. infra.md I-14.

### infra · APRENDIZAJE · MEDIO · Las sesiones de Odoo viven en disco efímero: cada reposo/deploy/reinicio vacía los carritos de la tienda
- Evidencia: `docker/entrypoint.sh:31` (`data_dir`), `docs/ARQUITECTURA.md` solo menciona el backend. Quien audite la tienda (@sitio-web) debe asumir que el carrito y el checkout en curso no sobreviven a un reinicio; no escalar a >1 instancia sin resolver sesiones compartidas. infra.md I-04.

### infra · HALLAZGO · MEDIO · `up media` (948 MB, 325 archivos) versionada: `.git` pesa 1,4 GB y cada job de CI la descarga
- Evidencia: `git ls-files "up media" | wc -l` = 325; `.dockerignore:13` la excluye de la imagen pero no de `actions/checkout` (`ci.yml:25,60,90,115,167`). Recomendación: `sparse-checkout` en CI; a mediano plazo moverla a R2/LFS. infra.md I-09.
