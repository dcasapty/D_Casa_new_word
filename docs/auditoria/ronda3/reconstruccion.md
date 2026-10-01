# Ronda 3 · r3-reconstruccion — ¿Adelgazar Odoo, reconstruir en Cloudflare o híbrido?

> Informe incremental (se escribe por partes; si está incompleto, el agente fue cortado).
> Agente: r3-reconstruccion · Fecha: 2026-10-01

## 0. Estado
- [ ] 1. Inventario real de lo que se usa de Odoo
- [ ] 2. Reconstrucción nativa por módulo (semanas, riesgo)
- [ ] 3. Alternativas intermedias (Odoo durmiente + borde; adelgazar)
- [ ] 4. Esquema D1 mínimo (`reconstruccion/esquema_d1.sql`, validado en SQLite)
- [ ] 5. TCO 12/24 meses + riesgo fiscal (FE DGI)
- [ ] 6. Recomendación con fases y criterios de salida

## 1. Inventario REAL de lo que D'CASA usa de Odoo (medido 2026-10-01)

### 1.1 Base `dcasa_test` (PostgreSQL 16 local, los 8 módulos instalados)

| Medida | Valor | Cómo |
|---|---|---|
| Módulos instalados | **108** (8 propios + 100 de Odoo arrastrados por dependencias) | `SELECT … FROM ir_module_module WHERE state='installed'` |
| Modelos (`ir_model`) | **538** | `SELECT count(*) FROM ir_model` |
| Tablas | **601** | `pg_tables` |
| Vistas (`ir_ui_view`) | **2 615** | |
| Tamaño de la base | **211 MB** | `pg_database_size` |
| … de eso, adjuntos | **120 MB** (71 MB `ir.ui.view` = assets compilados; 42 MB imágenes de `product.template` en 5 tamaños; 33 MB `product.image`) | `ir_attachment` agrupado; todo en BD (`store_fname` nulo) |
| Originales de imágenes de productos | 323 archivos, **30,5 MB** | `res_field = image_1920` |
| Datos de negocio | **0** facturas, **0** asientos, **0** ventas, **0** movimientos de stock, **0** movimientos de puntos, 5 contactos, 202 plantillas / 230 variantes, 118 cuentas, 3 impuestos, 10 diarios | conteos directos |
| Crons activos | **27** (solo 1 propio: «Socios: vencer canjes y regalos de cumpleaños», horario; 1 cada 10 min: `payment` post-process) | `ir_cron` |

Lecturas clave:
- **No hay datos transaccionales que migrar dentro del sistema nuevo** (aún no está en producción). El costo de migración
  hoy es casi cero en cualquier dirección; el día que se facture en serio deja de serlo. Esto es una **ventana**.
- La base está dominada por **metadatos de Odoo** (538 modelos, 2 615 vistas) para un negocio que usa ~20 entidades.
- Módulos arrastrados que el negocio **no** usa (por dependencia de `website_sale`, `crm`, `sale_management`…):
  `spreadsheet_dashboard_*` (6), `calendar*`, `sms`/`*_sms` (7), `snailmail*`, `iap*`, `crm_iap_*`, `partner_autocomplete`,
  `microsoft_outlook`, `google_gmail`, `sale_pdf_quote_builder`, `account_edi_ubl_cii`/`purchase_edi_ubl_bis3`/`sale_edi_ubl`
  (UBL europeo, no sirve a la DGI), `website_sale_comparison*`, `website_sale_wishlist`, `social_media`, `web_unsplash`,
  `auth_passkey*`, `digest`. Ver §3.2 sobre cuánto se puede adelgazar y cuánto no.

### 1.2 Dependencias declaradas (`addons/*/__manifest__.py`)

| Módulo | `depends` |
|---|---|
| `dcasa_base` | contacts, crm, sale_management, sale_stock, purchase, stock, account, l10n_pa |
| `dcasa_invoice` | dcasa_base, account, sale |
| `dcasa_socios` | dcasa_base, dcasa_invoice, sale_management, account, website_sale |
| `website_dcasa` | dcasa_base, dcasa_socios, website_sale |
| `dcasa_catalogo` | dcasa_base, website_dcasa, website_sale_stock |
| `dcasa_interfaz` | dcasa_catalogo, sale_management, stock, account, web_tour, mail_bot |
| `dcasa_contabilidad` | dcasa_base, dcasa_invoice, dcasa_interfaz, account, analytic, account_check_printing |
| `dcasa_brian` | dcasa_interfaz, dcasa_contabilidad, dcasa_catalogo, dcasa_socios, mail |

### 1.3 Código propio (líneas, sin `vendor/`)

| Módulo | Python | Tests py | XML | JS | SCSS | Modelos nuevos | `_inherit` | `super()` | xpath/position | parches JS | rutas HTTP | `sudo(` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dcasa_base | 284 | 145 | 118 | 0 | 58 | 0 | 2 | 1 | 3 | 0 | 0 | 1 |
| dcasa_invoice | 371 | 124 | 238 | 0 | 172 | 0 | 6 | 1 | **37** | 0 | 0 | 4 |
| dcasa_socios | 1 871 | 672 | 1 000 | 0 | 103 | 8 | 6 | **11** | 5 | 0 | 10 | **52** |
| website_dcasa | 648 | 462 | 869 | 226 | **1 923** | 0 | 6 | 4 | **29** | 0 | 3 | 6 |
| dcasa_catalogo | 318 (+4 676 JSON datos) | 150 | 139 | 0 | 20 | 0 | 3 | 2 | 16 | 0 | 0 | 0 |
| dcasa_interfaz | 237 | 161 | 280 | 465 | 986 | 1 | 1 | 0 | 4 | **5** | 0 | 0 |
| dcasa_contabilidad | 1 064 | 316 | 842 | 498 | 442 | 6 | 5 | 2 | 0 | 0 | 1 | 0 |
| dcasa_brian | **4 765** | 1 502 | 683 | 795 | 709 | 8 | 11 | 5 | 3 | 0 | 3 | 37 |
| **Total** | **≈ 9 560** | ≈ 3 530 | ≈ 4 170 | ≈ 1 980 | ≈ 4 410 | 23 | 40 | 26 | 97 | 5 | 17 | 100 |
| `edge/src` (TS) | 237 | | | | | | | | | | | |

(Conteo con `find … | wc -l`; incluye comentarios y líneas en blanco.)

### 1.4 Cuánto depende de internos de Odoo (acoplamiento)

| Pieza | Puntos de enganche con el core | Riesgo al actualizar Odoo |
|---|---|---|
| Puntos de socios | `account.move._invoice_paid_hook`, `_post`, `button_draft` (`dcasa_socios/models/account_move.py:15,31,41`); `sale.order.action_confirm` (`sale_order.py:32`); `res.partner.create/write`; `ir.http` | **Alto**: `_invoice_paid_hook` y `_post` son internos (cambian entre versiones mayores) |
| Factura | 37 xpath sobre el QWeb de factura/cotización, `ir.qweb.field.monetary`, `ir.actions.report` | Medio: los xpath se rompen si Odoo cambia la plantilla |
| Conciliación propia | `account.bank.statement.line`, `account.journal`; crea apuntes con el ORM de `account` | Medio |
| Reportes contables | SQL agrupado sobre `account_move_line` (lectura) | Bajo-medio (esquema estable) |
| Interfaz | 5 `patch(` de componentes OWL (`ActionHelper`, etc.; `sin_odoo.js`) | **Alto** (imports internos de OWL) |
| Sitio | 29 xpath sobre plantillas de `website_sale`; 1 923 líneas SCSS de marca | Medio |
| Brian | ~50 herramientas (`buscar_productos`, `crear_factura`, `registrar_pago`, `conciliar_movimiento`, `crear_cotizacion`, `ajustar_puntos`, `cambiar_rol_usuario`…) que llaman al ORM como el usuario real | Bajo para la lógica (ORM público), pero **Brian vive dentro de la transacción HTTP de Odoo** (hallazgo ronda 2 brian-eventos) |

### 1.5 Qué funciones usa el negocio de verdad (según código + docs; volumen real = 0 porque no está en producción)

| Función | ¿La usa / la necesita? | Dónde está hoy | Lo pone Odoo | Lo pone D'CASA |
|---|---|---|---|---|
| Ventas / cotizaciones | Sí, núcleo de la tienda física | `sale_management` + `dcasa_invoice`, `dcasa_socios` | Flujo cotización→pedido→factura, PDF, envío | Formato, canje de premio, padrino |
| Facturación + ITBMS 7 % | Sí, legal | `account`, `l10n_pa`, `dcasa_invoice` | Motor de impuestos, numeración, asientos, NC | Formato de marca, RUC/DV, monto en letras |
| Contabilidad (doble partida, reportes) | Sí (con contador) | `account` + `dcasa_contabilidad` | Asientos, plan `l10n_pa`, conciliación parcial, bloqueo de periodo | Reportes, conciliación UI, presupuestos, cheques |
| Conciliación bancaria / extractos CSV | Sí | `dcasa_contabilidad` (reemplazo de Enterprise) | Modelo de conciliación (`account.partial.reconcile`) | Pantalla, importador CSV |
| Cheques | Sí (pago a proveedores) | `account_check_printing` + `dcasa_contabilidad` | Numeración/estado | Formato y letras |
| Presupuestos | Sí (gerencia) | `dcasa_contabilidad` (`dcasa.presupuesto`) | — | Todo |
| Inventario | Sí, pero **sin costos** (E-02) y sin conteo inicial | `stock`, `sale_stock` | Movimientos, reservas, ubicaciones, valoración AVCO (sin configurar) | Nada propio |
| Compras | Declarado, sin uso real todavía | `purchase` | Todo | — |
| CRM | Arrastrado por `dcasa_base`; no hay flujo de CRM en el código | `crm` | — | — |
| Sitio + tienda | Sí | `website_sale` + `website_dcasa` + `dcasa_catalogo` | Carrito, checkout, constructor visual, SEO, pagos (sin pasarela real aún) | Marca, páginas, catálogo 199/202 productos |
| Socios | Sí | `dcasa_socios` (8 modelos propios) | Ficha `res.partner`, hook de factura pagada, portal web | Libro inmutable, canjes, PIN, antifraude |
| Brian | Sí (producto estrella según el dueño) | `dcasa_brian` | ORM, permisos (grupos), `mail` | Todo el agente |
| Factura electrónica DGI | **Obligatoria y no existe** | — | Nada en Community para Panamá | Pendiente (`l10n_pa_edi`) |

## 4. Esquema D1 mínimo (diseño, sin app) — `reconstruccion/esquema_d1.sql`

Archivos:
- `docs/auditoria/ronda3/reconstruccion/esquema_d1.sql` — 38 tablas, 19 triggers, 7 vistas, índices.
- `docs/auditoria/ronda3/reconstruccion/validar_esquema.py` — lo carga en SQLite en memoria y ejercita las
  invariantes con la factura real INV/2026/00821.

### 4.1 Validación (ejecutada 2026-10-01)

| Prueba | Resultado |
|---|---|
| `python3 validar_esquema.py` (SQLite 3.45.1, `:memory:`) | **38 tablas · 40 comprobaciones OK · 0 fallos** (exit 0) |
| Mismo esquema aplicado en **D1 local** (`wrangler 4.143.0 d1 execute --local`, motor workerd/miniflare del propio `edge/node_modules`, en el scratchpad, sin cuenta) | Aplica completo (39 objetos tabla incl. interna de D1, 19 triggers). Triggers `RAISE(ABORT)` → `SQLITE_CONSTRAINT_TRIGGER`; FK → `SQLITE_CONSTRAINT_FOREIGNKEY` (**D1 local hace cumplir FKs y triggers**). No se tocó la cuenta de Cloudflare. |

Lo que prueba el script (todo con centavos enteros):
- Factura 00821: 171,97 + 158,02 = **329,99**; ITBMS por línea 12,04 + 11,06 = **23,10**; total **353,09**; el
  balance de comprobación suma 0 y `v_itbms` devuelve 23,10 sobre base 329,99.
- No se publica un asiento descuadrado, sin número, con < 2 líneas o con fecha ≤ `fecha_bloqueo` (bloqueo de periodo).
- Lo publicado no se edita ni se borra (líneas, asiento, documento); la reversa exige motivo; la NC exige factura de origen y motivo.
- Conciliación parcial (cobro de 200,00 → quedan 153,09 abiertos), y rechazo de sobre-conciliar o conciliar cuentas distintas.
- Extracto bancario: huella única por diario (evita el duplicado y, con el ordinal del archivo, el problema C-08).
- Inventario: movimientos inmutables, existencia derivada (10 − 1 = 9), AVCO (5 × 90 + 5 × 110) / 10 = 100,00 en historial solo-anexar.
- Socios: libro solo-anexar sin columna de saldo (saldo = `SUM`), contrario exacto y único, referido pagado una sola vez
  por compra, padrino escrito una vez, un canje pendiente por premio. **Las cifras de puntos del script son de prueba**:
  las reales siguen viviendo solo en `puntos.json` (regla 1).
- Auditoría y `outbox` (cola de salida a PAC/Odoo/WhatsApp) con idempotencia por `clave_idem`.

### 4.2 Decisiones de diseño y por qué

1. **Dinero en centavos enteros** y cantidades en milésimas: SQLite no tiene `NUMERIC` exacto; `REAL` no sirve para dinero.
2. **Triggers como última defensa**, no como lógica de negocio: el cálculo (ITBMS por línea, AVCO, puntos) vive en
   TypeScript con pruebas; la base solo garantiza invariantes que nunca deben romperse.
3. **D1 no tiene transacciones interactivas.** `batch()` es atómico («Batched statements are SQL transactions… If a
   statement in the sequence fails… it aborts or rolls back the entire sequence», https://developers.cloudflare.com/d1/worker-api/d1-database/,
   dateModified 2026-06-22), pero no se puede *leer y decidir* dentro de la transacción. Para numeración correlativa
   de facturas, AVCO y saldo de puntos al canjear (leer → calcular → escribir) hay dos caminos:
   - **Durable Object «Libro» único** (SQLite dentro del DO): un solo hilo, escritura coalescida atómica y
     `transaction()`; «Output gates hold outgoing network messages… until pending storage writes complete»
     (https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/). Con el volumen de D'CASA
     (decenas de facturas al día) un solo DO sobra (≈200 req/s aun bloqueando 5 ms por petición, misma página).
     PITR de 30 días (https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/, 2026-09-21 según r3-cf-plataforma).
   - **D1 + `batch()` con escrituras condicionales** (`INSERT … SELECT … WHERE` + `UNIQUE`) y reintento: más simple de
     consultar desde fuera (HTTP API, export), pero más fácil de equivocarse.
   - Recomendación técnica si se reconstruye: **libro contable, stock y puntos dentro de un DO** (serialización
     garantizada); **catálogo, sitio y lecturas en D1** (réplicas de lectura, export). Idempotencia con `clave_idem`
     en ambos.
4. **Imágenes en R2**, nunca en la base (hoy 75 MB de imágenes y 71 MB de assets viven en PostgreSQL).
5. **Campos de FE DGI ya previstos** (`fe_estado`, `fe_cufe`, `fe_qr`, XML/PDF en R2) y `outbox` para el PAC.

### 4.3 Límites oficiales de D1 / DO relevantes

| Dato | Valor | Fuente |
|---|---|---|
| Precio D1 (Paid) | 25 000 M filas leídas/mes y 50 M escritas incluidas; 5 GB incluidos, +$0,75/GB-mes; sin egress | https://developers.cloudflare.com/workers/platform/pricing/ (Last updated 2026-08-28) |
| Réplicas de lectura | Sin costo extra; consistencia secuencial con Sessions API | https://developers.cloudflare.com/d1/best-practices/read-replication/ |
| Tamaño máx. por base | 10 GB (Paid) / 500 MB (Free); 1 TB por cuenta | repo oficial `cloudflare-docs` `d1/platform/limits.mdx` (leído por r3-cf-plataforma; el buscador del MCP no devuelve esa página) |
| Time Travel (PITR) | 30 días (Paid) / 7 (Free) | repo oficial `d1/reference/time-travel.mdx` (ídem) |
| DO SQLite | hasta 10 GB por objeto; PITR 30 días con bookmarks | https://developers.cloudflare.com/durable-objects/concepts/what-are-durable-objects/ ; …/api/sqlite-storage-api/ |
| DO precio (Paid) | 1 M req/mes incl. (+$0,15/M); 400 000 GB-s incl. (+$12,50/M GB-s); SQL igual que D1 pero almacenamiento $0,20/GB-mes | https://developers.cloudflare.com/durable-objects/platform/pricing/ |

Dimensionamiento: 211 MB de `dcasa_test` son casi todo metadatos de Odoo y binarios. Los datos de negocio de D'CASA
(estimación propia: 200 productos, ~10 000 facturas/año × ~3 líneas, ~5 asientos-línea por factura) caben en
**decenas de MB por año** en D1/DO: el límite de 10 GB no es una restricción realista en 10 años.

