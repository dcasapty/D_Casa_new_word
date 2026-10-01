# D'CASA — Decisión de arquitectura y plan de implementación

Síntesis de tres rondas de auditoría (9 + 5 + 8 agentes). Detalle y evidencia en
`INFORME_FINAL.md`, `ronda2/` y `ronda3/`. Fecha: 2026-10-01.

## Lo que ya decidió el dueño

| Tema | Decisión |
|---|---|
| Base de datos gestionada Neon | Descartada (costo) |
| Reconstruir todo fuera de Odoo | No: Odoo 19 se queda como back-office (contabilidad, facturación, inventario, CRM) |
| Precios del catálogo | Los del Excel son **sin ITBMS**; la web muestra «$39.99 + ITBMS» |
| IA de Brian | Meta Muse Spark nivel `-contributor` como principal (acepta que entrena con los prompts); Claude como respaldo |
| CRM | Se queda y se mejora con un módulo propio; Brian forma parte del CRM |
| Módulos sobrantes | Se desinstalan SMS, snailmail, IAP/autocompletar, UBL europeo, tableros, lista de deseos, comparador, `base_import_module` |

## Datos medidos que deciden la infraestructura

- **Odoo real** (8 módulos + catálogo, `ronda3/odoo-medicion.md`): 169 MiB de RAM en reposo, ~373 MiB de pico
  tras un despliegue; Odoo + PostgreSQL ≈ **400 MiB** de pico ⇒ cabe en el contenedor **basic (1 GiB)**.
  Arranque ~3 s. En reposo ~0,9 s de CPU por hora. Base: 211 MB (91 MB sin adjuntos).
- **Fallo encontrado**: con `db_maxconn=16` (`docker/entrypoint.sh`) y 20-50 peticiones simultáneas,
  ~75 % responde 500 (`PoolError`). Se corrige en la Fase 0.
- **PostgreSQL efímero + WAL a R2** (`ronda3/datos.md`, 12 ensayos de «muerte» del contenedor):
  0 filas corruptas; con la corrección `CHECKPOINT` tras restaurar, **RPO ≤ 52 s (mediana 33 s)** y
  **RTO ≈ 46 s** (con almacenamiento local; con R2 real será algo mayor, sin medir).
- **Costos oficiales de Cloudflare** (`ronda3/cf-plataforma.md`): Containers cobra memoria y disco
  aprovisionados + CPU usada. basic 24/7 ≈ **$12/mes con el plan de $5 incluido**. Sitio estático, Brian,
  colas, R2, D1 y logs caben dentro de los $5. El cron `*/10` del Worker impide que el contenedor duerma.
- **Sitio estático** (`ronda3/sitio-edge.md`): Lighthouse móvil 39-55 → 99-100, LCP 8-11 s → 1,6-2,2 s, $0.
- **Brian** (`ronda3/brian-*.md`): capa Cloudflare ≈ $0; el gasto son tokens (≈ $19/mes a 50 interacciones
  diarias con 80 % Meta; precio de Meta sin verificar). Motor de documentos propio: 49/49 pruebas.

## La decisión pendiente: dónde vive Odoo y su base

| | **A · Todo en Cloudflare** | **B · Cloudflare + PG gestionado** | **C · VPS + Cloudflare delante** |
|---|---|---|---|
| Qué es | Odoo + PostgreSQL en un Container basic 24/7; WAL continuo a R2 + `pg_dump` diario a R2 | Odoo en Container basic; PostgreSQL en PlanetScale PS-5 (con PITR) | Odoo + PostgreSQL en un VPS (Hetzner/DigitalOcean); Tunnel + Access gratis; respaldos a R2 |
| Costo mensual | **≈ $12** + centavos de R2 | ≈ $17 | ≈ $12-17 (UE) / $20-29 (EE. UU.) |
| Pérdida máxima si muere de golpe | ≤ ~1 min (medido) | segundos (PITR del proveedor) | ~0 (disco persistente) + WAL a R2 |
| Plataformas a operar | 1 | 2 | 2 (VPS lo administras tú) |
| Riesgos | Diseño poco convencional (base en disco efímero); cada reinicio = restauración (~1 min); snapshots en beta; los reinicios de host desconectan sesiones | PS-5 = 1/16 vCPU (sin medir con Odoo); latencia Container↔BD sin medir; precio NO VERIFICADO | Parches y seguridad del servidor a tu cargo; latencia Panamá↔Europa |

**Recomendación: A**, porque es la más barata, todo vive en Cloudflare y su riesgo principal ya se
midió. La condición es probarla 2 semanas en un entorno de prueba con simulacros de caída y
restauración antes de cargar facturas reales. Si un simulacro falla o el RTO con R2 real pasa de 5 min,
se pasa a **C**: el respaldo a R2 es el mismo, así que el cambio es barato. Hay que aceptar
explícitamente el RPO de ~1 minuto.

## Plan de implementación por fases

Cada fase lleva tests y se verifica antes de pasar a la siguiente. Todo el código va a `addons/`,
`edge/`, `docker/` y `.github/`, nunca a `vendor/odoo`.

### Fase 0 — Seguridad y correcciones (≈ 1-2 semanas) · bloquea todo lo demás
1. Cerrar la superficie RPC confirmada en Odoo real: B-01..B-04, S-01, S-02, S-09, C-07
   (`@api.private`, `_` o control de grupo) + un test que falle si aparece un método público con `sudo()`.
2. ITBMS: impuesto «se suma al precio», `list_price` = Excel, leyenda «+ ITBMS» en la web; corregir tests,
   `docs/CATALOGO.md` y la herramienta `crear_producto` de Brian.
3. CI y arranque: no sobrescribir `DCASA_PIN_PEPPER` si falla `wrangler secret list` (S-03), cerrar la
   ventana `admin/admin` (S-04), bloquear `/jsonrpc` y `/json/2` de base de datos en el borde (S-07),
   `db_maxconn` adecuado, quitar el cron `*/10`.
4. Roles Vendedora y Gerencia; ocultar reportes antifraude y limitar descuentos.
5. Desinstalar los módulos sobrantes acordados.
6. Rápidos del sitio: `loading="eager"` en el hero, JSON-LD y `web.base.url`, «All Products» traducido.

### Fase 0b — Legal y fiscal (en paralelo, desde ya)
- Factura electrónica DGI: elegir PAC y módulo de Odoo 19 (bloqueante legal para producción).
- Política de privacidad y cookies, páginas de entregas/garantía/términos, razón social y RUC en el pie;
  retirar «financiamiento» y «tarjeta» mientras no existan.

### Fase 1 — Infraestructura en Cloudflare (≈ 2-3 semanas)
1. Imagen con PostgreSQL + pgBackRest → R2, `CHECKPOINT` tras restaurar y vigilante `pg_switch_wal()`;
   `pg_dump` diario a R2; restauración automática probada en CI.
2. Container basic con scheduling `durable_object`, sesiones de Odoo fuera del disco efímero.
3. Entorno de prueba + 2 semanas de simulacros. Criterio de salida: 0 pérdida fuera del RPO acordado y
   RTO < 5 min con R2 real.

### Fase 2 — Sitio y tienda en el borde (≈ 3-4 semanas)
Generador estático desde Odoo (mismas URLs para no perder SEO), variantes de imagen en el build,
Worker con `run_worker_first` para `/socios`, `/web`, `/my`, `/brian`; reconstrucción al cambiar un
producto. Criterio: Lighthouse móvil ≥ 90 y LCP < 2,5 s.

### Fase 3 — Brian, primera mejora (dentro de Odoo, ≈ 2-3 semanas)
Proveedor `meta` propio con Claude de respaldo, registro de uso de tokens y topes, prefijo estable para
caché, herramienta `leer_archivo` con el motor de documentos, importación de Excel con vista previa,
confirmación y deshacer. Corregir las herramientas defectuosas (descuento libre, WhatsApp que no envía).

### Fase 4 — Brian completo (≈ 4-6 semanas)
Paquetes de habilidades bajo demanda, niveles de ayuda por rol configurables por el admin,
aprendizaje con aprobación de gerencia, paquete CRM (oportunidades desde WhatsApp, seguimientos),
compras y entregas; migración progresiva al borde (Durable Objects + Workflows) con el bucle de Odoo
como respaldo. Evals en CI con los 59 casos dorados.

### Fase 5 — Inventario y contabilidad «muy buenos»
Costos y valoración AVCO, conteo inicial, reglas de reorden, antigüedad de saldos y cobranza,
bloqueo de periodos, y lo que siga del orden de `enterprise-gap.md`.

## Qué necesito del dueño para arrancar
1. ~~Elegir A, B o C~~ → **Elegida A** (2026-10-01): Odoo + PostgreSQL en Container basic con WAL a R2; RPO aceptado ≈ 1 min.
2. ~~Visto bueno Fase 0~~ → **Aprobada** (2026-10-01); en curso con 5 agentes en paralelo (worktrees).
3. Contador o asesor para el PAC de la DGI y los textos legales.

## Pendientes conocidos
- `r3-odoo-medicion` y `r3-datos` se cortaron por el límite de uso de la sesión antes de cerrar sus
  informes; sus mediciones están en sus archivos y en `BITACORA.md`. Falta medir el RTO con R2 real y el
  arranque con cuota de CPU de basic.
- Precios de Meta, Hetzner y PlanetScale sin verificar en fuente primaria.
- Dos fixtures de 57 MB quedaron en el historial de la rama: limpiar antes de llevar a `main`.
