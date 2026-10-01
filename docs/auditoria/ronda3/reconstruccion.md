# Ronda 3 · r3-reconstruccion — ¿Adelgazar Odoo, reconstruir en Cloudflare o híbrido?

> Informe incremental (se escribe por partes; si está incompleto, el agente fue cortado).
> Agente: r3-reconstruccion · Fecha: 2026-10-01

## 0. Resumen ejecutivo

**Recomendación: híbrido por fases (camino 3).** Odoo 19 Community adelgazado se queda como back-office contable,
fiscal y de inventario; sitio/tienda, Brian y (si Odoo va a dormir) socios salen al borde de Cloudflare.
**No reconstruir todo ahora.**

| | 1a Odoo adelgazado (VPS) | 2 Reconstrucción total nativa | 3 Híbrido por fases |
|---|---|---|---|
| Infra/mes | $12–17 | $5–7 (al terminar) | $12–17 |
| Semanas de desarrollo (1 persona + Claude Code) | 9–16 a producción | **57–83** (con ×1,5) + FE | 19–31 |
| TCO 12 meses (hora a $15, SUPUESTO) | $7,5–12,3 k | $33,1–36,2 k (sin terminar) | $12,8–21,1 k |
| TCO 24 meses | **$12,2–19,5 k** | **$45,2–66,3 k** | **$17,6–27,6 k** |
| Riesgo contable/fiscal | Bajo (motor probado) | Alto (100 % propio) | Bajo |
| Sitio rápido y cacheable | No | Sí | Sí |
| Brian por eventos | No | Sí | Sí |

Datos que deciden:
1. **Medido**: D'CASA usa ~20 entidades sobre 108 módulos / 538 modelos / 601 tablas de Odoo, con ≈ 9 560 líneas de
   Python propio, y **0 transacciones** todavía (la migración hoy es casi gratis; deja de serlo con la primera factura real).
2. **Oficial**: todo nativo cuesta ≈ $5/mes (Workers Paid); Odoo en VPS ≈ $12–17. El ahorro (~$84–144/año) **nunca**
   paga las ~2 000–3 000 horas extra de reconstruir.
3. **Fiscal**: la FE DGI con PAC es obligatoria por encima de B/. 36 000/año o 100 documentos/mes (fuentes
   secundarias) y existe un módulo de FE Panamá para Odoo 19 (NO VERIFICADO): **es más fácil y seguro dentro de Odoo**.
4. **Diseño listo por si un día se reconstruye**: esquema D1 de 38 tablas con libro contable de doble partida,
   ITBMS, conciliación, bloqueo de periodo, inventario AVCO, ventas y libro de puntos inmutable, validado en SQLite
   (40/40) y en D1 local (triggers y FK se cumplen).

Archivos de este agente: `reconstruccion/esquema_d1.sql`, `reconstruccion/validar_esquema.py`, `reconstruccion/tco.py`.

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

## 2. Reconstrucción nativa en Cloudflare (Workers + D1 + DO + R2 + Queues/Workflows + Static Assets)

### 2.1 Supuestos explícitos de la estimación

- **1 programador (el dueño) a tiempo completo, 40 h/semana, con Claude Code.** Las semanas ya suponen la
  aceleración de Claude Code (sin ella, × 1,5–2). Pila: TypeScript, Hono (rutas), Drizzle o SQL a mano (D1/DO),
  Static Assets para el sitio, R2 para binarios, Queues/Workflows para trabajos, Durable Object «Libro».
- Paridad funcional con **lo que D'CASA usa hoy** (tabla §1.5), no con Odoo entero.
- «Semanas» = trabajo terminado con pruebas, no prototipo. Rango bajo = todo sale bien; alto = realista.
- **Factor de riesgo de planificación × 1,5** sobre el total (un solo programador, sin revisor, dominio contable):
  regla prudente propia, no un dato medido.
- No incluye la factura electrónica DGI (se cuenta aparte en §5 porque cuesta parecido en ambos caminos).

### 2.2 Por módulo funcional

| # | Módulo | Qué hay que construir que hoy pone Odoo | Complejidad | Riesgo | Semanas |
|---|---|---|---|---|---|
| 1 | Plataforma del panel | Login, roles, permisos por registro, auditoría, **kit de pantallas** (listas con filtro/orden/agrupar, formularios, búsqueda, exportar Excel/CSV, importar), **PDF** (en Workers no hay wkhtmltopdf: Browser Rendering o PDF en el cliente), correo saliente, adjuntos en R2 | Alta (es «el Odoo» que no se ve) | Medio | 4–6 |
| 2 | Clientes/terceros | Ficha, RUC/DV, celular llave, búsqueda, fusión de duplicados | Baja | Bajo | 1 |
| 3 | Catálogo y precios | Plantillas/variantes/atributos, combos, listas de precio, imágenes R2 (redimensión con Images), importación del Excel | Media | Bajo | 2–3 |
| 4 | Ventas/cotizaciones | Flujo cotización→enviada→confirmada→facturada, descuentos con tope por rol, PDF de cotización, envío por WhatsApp, reservas de stock | Media | Medio | 3–4 |
| 5 | Facturación + ITBMS | Documentos, NC total/parcial, numeración correlativa sin huecos (DO), ITBMS por línea, factura de marca en PDF, monto en letras (ya existe en Python: portar) | Media-alta | **Alto** (fiscal) | 3–4 |
| 6 | Contabilidad | Motor de doble partida, importar plan `l10n_pa`, pagos, conciliación parcial y bancaria, extractos CSV, bloqueo de periodo, cierre, reportes (ER, BG, comprobación, mayor, ITBMS, antigüedad), presupuestos, cheques | Alta | **Alto** (un error contable es silencioso) | 6–9 |
| 7 | Inventario | Movimientos, ubicaciones, recepciones, conteo, AVCO, valoración contable automática, costos de importación (flete/aduana) | Alta | Alto | 4–6 |
| 8 | Compras | Órdenes de compra, recepción, factura de proveedor, pagos/cheques | Media | Medio | 2–3 |
| 9 | Sitio + tienda | Páginas, catálogo público, SEO/sitemap, carrito, checkout, pasarela (Yappy/tarjeta), entregas, cuentas de cliente, edición de contenido (**sin el constructor visual de Odoo**) | Media-alta | Medio | 4–6 |
| 10 | Socios | Portar `dcasa_socios` (reglas y 79 pruebas existen; el diseño ya es «libro + reglas en JSON») | Media | Bajo-medio | 3–4 |
| 11 | Brian | Portar el bucle (4 765 líneas) y 45 herramientas a la API nueva; los agentes r3-brian-* ya proponen moverlo al borde en cualquier caso | Media-alta | Medio | 4–6 |
| 12 | Migración, paralelo, capacitación | Cargar catálogo/clientes/saldos, correr 1 mes en paralelo, manuales | Media | Medio | 2–3 |
| | **Subtotal** | | | | **38–55** |
| | **Con factor × 1,5** | | | | **57–83 semanas ≈ 1,1–1,6 años** |
| | Horas (40 h/sem) | | | | **2 280–3 320 h** |

Comparación de tamaño: hoy D'CASA tiene ≈ 9 560 líneas Python propias apoyadas en ~100 módulos de Odoo. Una
reconstrucción con paridad razonable es, por experiencia de proyectos parecidos, **3–5 veces** ese código propio
(estimación, NO medida): ≈ 30 000–45 000 líneas de TypeScript + pruebas, mantenidas por una sola persona.

### 2.3 Lo que se pierde al salir de Odoo

| Se pierde | Por qué importa a D'CASA |
|---|---|
| **Motor contable probado** (millones de instalaciones): redondeos, NC, conciliación parcial, diferencias, cierres | El riesgo contable pasa a ser 100 % propio; el contador ya no puede «auditar contra Odoo» |
| **Localización `l10n_pa`** (plan de cuentas, impuestos) mantenida por Odoo | Hay que copiarla y mantenerla a mano |
| **Módulos de FE Panamá de terceros** (p. ej. `l10n_pa_factura_electronica` v19 en la tienda de Odoo con PAC HKA/WEBPOS/EBIPAC, NO VERIFICADO: apps.odoo.com bloqueado) | Con código propio la FE se integra desde cero con la API del PAC |
| Actualizaciones de seguridad y corrección de Odoo/OCA | Odoo 19 tiene soporte estándar hasta ~sep-2028 (fuentes secundarias, NO VERIFICADO en odoo.com) |
| Ecosistema OCA (conciliación, reportes, POS, nómina, activos…) y contadores que conocen Odoo | Cada función nueva = escribirla |
| **Constructor visual del sitio** (la dueña edita sola) | En nativo, el contenido se edita con un CMS mínimo propio o en git |
| Pantallas genéricas gratis (listas, filtros, pivotes, exportar, importar) | Es el módulo 1 de la tabla: 4–6 semanas solo para igualarlo |

### 2.4 Lo que se gana

| Se gana | Cuánto (con fuente o medición) |
|---|---|
| **Costo de infraestructura** | ≈ **$5/mes** (Workers Paid incluye 10 M req, 30 M ms CPU; D1 5 GB y 25 000 M lecturas; Static Assets gratis e ilimitados; https://developers.cloudflare.com/workers/platform/pricing/, Last updated 2026-08-28) frente a $12–55/mes de Odoo (§5) |
| **Rendimiento** | Páginas desde Static Assets/caché en el PoP más cercano; sin arranque en frío de 1–3 s del contenedor; sin el problema CSRF/cookie que impide cachear el HTML de Odoo (medido por r3-sitio-edge) |
| **Control total** | Modelo de datos de ~38 tablas en vez de 601; sin internos de Odoo que se rompan al actualizar (26 `super()`, 97 xpath, 5 parches OWL hoy) |
| **Brian nativo** | Agentes por eventos en DO/Workflows sin la transacción HTTP de Odoo abierta (hallazgo brian-eventos, ronda 2) |
| Superficie de ataque menor | Desaparece la familia «método público + sudo() por RPC» (S-01, S-02, B-01..B-04) porque no hay RPC genérico |
| Sin servidor que operar | Sin VPS, sin parches de SO, sin PostgreSQL que respaldar (Time Travel 30 días incluido) |

## 3. Alternativas intermedias

### 3.1 Odoo como back-office que duerme + sitio/tienda, socios y Brian en el borde

Idea: el público (sitio, tienda, app de socios, webhooks de Telegram/pasarela) **nunca** despierta a Odoo; Odoo solo
lo usan la tienda física y el contador en horario. Requisito duro, medido por r3-sitio-edge y confirmado por
r3-cf-plataforma: mientras el HTML del sitio salga de Odoo (cookie de sesión + CSRF por sesión), **cada visita o bot
despierta el contenedor** y «dormir» no existe. Por eso el primer paso es sacar el sitio.

| Función en el borde | ¿Necesita a Odoo despierto? | Cómo se resuelve |
|---|---|---|
| Páginas y catálogo público | No | Odoo publica (al guardar un producto o por cron) un JSON/HTML a Static Assets/R2/D1; el Worker sirve. Purga por tag. |
| Precio y stock mostrados | No (consistencia eventual) | Instantánea publicada; el stock web es un «cupo» en un DO que se recarga al sincronizar |
| Carrito | No | Cookie firmada o DO por carrito; sin sesión de Odoo (hoy se pierde en cada siesta: r3-cf-plataforma) |
| Checkout + pago | **No para cobrar**; sí para facturar | La pasarela llama al Worker (webhook); el pedido queda en D1 + `outbox`; una Queue lo entrega a Odoo (`sale.order`) cuando despierta; idempotente por `clave_idem` |
| Factura del pedido web / FE DGI | Sí (si la FE la emite Odoo) | Se emite al despertar (mismo día hábil). **Plazo legal de emisión por verificar con el contador** |
| App de socios: saldo, actividad | Depende de dónde viva el libro | (a) Libro en Odoo → el borde muestra una instantánea (saldo «al cierre de ayer»); (b) **libro movido al borde (DO)** → siempre en vivo, Odoo envía el evento «factura pagada/anulada» por la cola |
| Socios: registro, PIN, candado | No | DO por socio; la pimienta como secreto del Worker (regla 6) |
| Socios: canje | Sí con (a); no con (b) | Con (b) el canje reserva puntos en el DO y la venta en tienda lo cobra igual que hoy |
| Brian: conversación, memoria, archivos, costo | No | Agente en DO/Workflows (diseño de r3-brian-agente) |
| Brian: herramientas que leen/escriben el ERP | **Sí** | Encolar y despertar Odoo bajo demanda (1–3 s del contenedor + arranque de Odoo, ver r3-odoo-medicion), o limitar Brian a horario de tienda |
| Telegram / MCP de Brian | No para recibir | El Worker responde 200 al instante y encola (arregla además el webhook que hoy espera al modelo) |

Sincronización (patrón *outbox* + cola, ver tabla `outbox` del esquema):
- **Borde → Odoo**: pedidos web, registros de socios, canjes, tareas de Brian. Cola con reintentos; el consumidor
  despierta el contenedor (o llama al VPS por Tunnel) y crea los registros con una **cuenta de servicio con permisos
  mínimos** (hoy no existe: hallazgo brian-eventos ronda 2). Idempotencia por `clave_idem` guardada en Odoo.
- **Odoo → borde**: catálogo/precios/stock publicados, facturas pagadas (para puntos), estado de pedidos. Un cron de
  Odoo (solo cuando está despierto) o un hook al guardar empuja al Worker.
- Conflictos: solo hay un dueño por dato (catálogo y contabilidad = Odoo; carrito, socios (b) y Brian = borde). Sin
  escritura en dos sitios, no hay conflicto que resolver.

Costo: el borde cabe en los $5 de Workers Paid (r3-brian-agente, r3-cf-plataforma). Odoo pasa a horario (12 h × 26 d)
o a VPS (§5).

### 3.2 Adelgazar Odoo (opción 1 pura)

Medido en `dcasa_test`: de 108 módulos instalados, **67 se instalan solos** (`auto_install`) por combinación de
dependencias. Lo que se puede quitar sin perder funciones que D'CASA usa:

| Quitar | Arrastra | Cómo |
|---|---|---|
| `crm` de `dcasa_base` (no hay flujo de CRM en el código propio) | `crm`, `sale_crm`, `crm_iap_*`, `iap_crm`, `crm_sms`, `website_crm`, `website_crm_sms`, `sales_team` (parcial) | Quitar de `depends` + desinstalar |
| SMS/IAP/snailmail/autocompletar | `sms`, `*_sms` (7), `snailmail*`, `iap*`, `partner_autocomplete` | Desinstalar (algunos vuelven si otro módulo los exige: probar) |
| UBL europeo | `account_edi_ubl_cii`, `purchase_edi_ubl_bis3`, `sale_edi_ubl` | No sirve a la DGI |
| Tableros de hoja de cálculo | `spreadsheet_dashboard_*` (6), `spreadsheet_account` | Si se usan los reportes de `dcasa_contabilidad` |
| Comparador y favoritos de la tienda | `website_sale_comparison*`, `website_sale_wishlist`, `website_sale_stock_wishlist` | Desinstalar |
| Correo de Google/Microsoft, passkeys | `google_gmail`, `microsoft_outlook`, `auth_passkey*` | Si se usa SMTP propio |

Efecto esperado: menos tablas, menos vistas, menos JS en el panel y arranque algo más rápido. **No cambia el orden de
magnitud del costo**: la memoria se cobra por tipo de instancia aprovisionada (r3-cf-plataforma: 75–85 % del costo
del contenedor) y Odoo + PostgreSQL siguen necesitando ≈ 1–4 GiB. La cifra de RAM/arranque antes y después la mide
r3-odoo-medicion; aquí no se inventa. Riesgo: algunos `auto_install` reaparecen al actualizar; hay que fijarlo con
una prueba que falle si se reinstalan.

Otras piezas pesadas reemplazables sin salir de Odoo:
- Imágenes y assets fuera de PostgreSQL (hoy 120 MB en la base): R2 vía Worker/Images, base más chica y respaldos más rápidos.
- PDF con wkhtmltopdf dentro del contenedor (imagen grande): mantener; reemplazar no compensa.
- Sesiones en disco efímero: si se queda en Container, guardar sesiones en la base o aceptar re-login.

## 5. TCO a 12 y 24 meses y riesgo legal/fiscal

Script reproducible: `docs/auditoria/ronda3/reconstruccion/tco.py` (todas las entradas arriba del archivo; cambia
`VALOR_HORA` y vuelve a correr). Supuestos:
- **Valor de la hora del dueño-programador: $15/h (SUPUESTO, costo de oportunidad, no medido).** 40 h/semana, 46 semanas útiles/año.
- Infraestructura (USD/mes): Workers Paid $5 (oficial, pricing Last updated 2026-08-28); Odoo en VPS + Tunnel + R2 de
  respaldos $7–12 sin el Worker (ronda 2 `cf-costos.md` §6, precios de Hetzner que **subieron en 2026: revalidar al
  contratar**); Container standard-1 24/7 CPU 10 % $29,24 sin el plan (r3-cf-plataforma, script `costos_containers.py`);
  Neon 24/7 ≈ $19,8 (ronda 2); nativo $5 + $0–2 (D1/DO/R2/Queues dentro de lo incluido para este volumen, §4.3).
- Horas: tablas §2.2 y §6 (fases). Mantenimiento: 4 h/sem Odoo, 6 h/sem nativo (código 100 % propio), 5 h/sem híbrido.
- Riesgo cuantificado = probabilidad × impacto (SUPUESTOS declarados en el script): migración de Odoo que se duplica
  (p = 0,3), reconstrucción que se pasa un 30 % (p = 0,5), error contable material en código propio (p = 0,3 × $1 000–3 000),
  error de sincronización borde↔Odoo (p = 0,2 × $500).
- Fuera de la cuenta (iguales en los tres): tokens de IA de Brian, dominio, correo, **tarifa del PAC** (por documento,
  NO VERIFICADA: varía por proveedor).

### 5.1 Resultado (USD; salida de `tco.py` del 2026-10-01)

| Camino | Meses | Infra | Horas | Horas en USD | Riesgo | **Total** |
|---|---|---|---|---|---|---|
| 1a · Odoo adelgazado en **VPS** | 12 | 144–204 | 480–788 | 7 200–11 820 | 162–324 | **7 506–12 348** |
| | 24 | 288–408 | 760–1 200 | 11 400–18 000 | 540–1 080 | **12 228–19 488** |
| 1b · Odoo adelgazado en **Container 24/7 + Neon** | 12 | 648 | 480–788 | 7 200–11 820 | 162–324 | **8 010–12 792** |
| | 24 | 1 297 | 760–1 200 | 11 400–18 000 | 540–1 080 | **13 237–20 377** |
| 2 · **Reconstrucción total** nativa | 12 | 144–204 | 1 840 | 27 600 | 5 400–8 400 | **33 144–36 204** (no terminada) |
| | 24 | 225–318 | 2 640–3 836 | 39 600–57 540 | 5 400–8 400 | **45 225–66 258** |
| 3 · **Híbrido por fases** (Odoo back-office en VPS + borde) | 12 | 144–204 | 835–1 375 | 12 525–20 625 | 138–246 | **12 807–21 075** |
| | 24 | 288–408 | 1 125–1 755 | 16 875–26 325 | 460–820 | **17 623–27 553** |

### 5.2 Lo que dicen los números

1. **La infraestructura es lo de menos.** Entre Odoo en VPS ($12–17/mes con Worker) y todo nativo ($5–7/mes) la
   diferencia es **$7–12/mes ≈ $84–144/año**. Aun contra el peor caso (Container 24/7 + Neon, ≈ $54/mes) el ahorro
   nativo es ≈ $590/año. Las ≈ 2 000–3 000 horas extra de la reconstrucción (≈ $30 000–45 000 a $15/h) **no se
   recuperan nunca** por ahorro de infraestructura (≥ 50 años de *payback* en el mejor caso).
2. **Aunque la hora valiera $0** (el dueño programa «gratis»), el costo real de reconstruir es **tiempo de calendario**:
   1,1–1,6 años con una persona antes de tener paridad, con el negocio esperando o corriendo sobre Odoo de todas formas.
3. **El híbrido cuesta ≈ $5 000–8 000 más que 1a en 24 meses** y a cambio compra: sitio rápido y cacheable en el
   borde, Brian por eventos (que el dueño considera el producto principal), socios siempre en línea, y menos
   superficie de Odoo que migrar. Ese sobrecosto es casi todo trabajo que los agentes r3-brian-* y r3-sitio-edge
   proponen hacer de todos modos.
4. **El Container 24/7 no tiene sentido** si se queda Odoo entero: cuesta 4× el VPS por lo mismo (ver r3-datos y
   r3-cf-plataforma sobre dónde vive PostgreSQL; aquí solo se usa como comparación).

### 5.3 Riesgo legal/fiscal: factura electrónica DGI (SFEP)

Hechos (fuentes secundarias, NO VERIFICADO en dgi.mef.gob.pa por bloqueo/tiempo):
- Resolución DGI **201-6299 de 29-07-2025**, vigente desde **01-01-2026**: el *Facturador Gratuito* queda para
  contribuyentes con ingresos ≤ B/. 36 000/año **y** ≤ 100 documentos/mes; por encima, **PAC obligatorio**
  ([Alegra](https://blog.alegra.com/panama/facturacion-electronica-panama/), [FacturaHQ](https://facturahq.cloud/es/facturacion-electronica-panama/)).
  Una mueblería con tienda física y web casi seguro supera ambos umbrales ⇒ **PAC**. Confirmar con el contador.
- El PAC valida y devuelve la autorización (CUFE/CAFE); la integración es una API HTTP del PAC (XML firmado + QR).
- Existen módulos de FE Panamá para Odoo en la tienda oficial, incl. `l10n_pa_factura_electronica` para **v19**, que
  conecta con PAC (HKA, WEBPOS, EBIPAC según la ficha de la versión POS) — [apps.odoo.com](https://apps.odoo.com/apps/modules/19.0/l10n_pa_factura_electronica)
  (bloqueado por el proxy: autor, precio, licencia y compatibilidad con Community **NO VERIFICADOS**).

¿Más fácil con Odoo o con código propio?

| Aspecto | Odoo | Código propio |
|---|---|---|
| Módulo listo | Sí existen (de terceros, de pago probablemente, calidad por verificar) | No; desde cero |
| Datos que pide el XML (RUC/DV, tasas por ítem, NC referenciada, CUFE) | El modelo `account.move` ya los tiene; `dcasa_base` ya guarda RUC/DV | El esquema §4 ya prevé `fe_*`, ITBMS por línea y NC con origen |
| Esfuerzo propio si se integra con la API del PAC | 3–6 semanas (módulo `l10n_pa_edi` heredando `account.move`) | 3–6 semanas (cliente HTTP + firma + cola `outbox`) |
| Riesgo de rechazo/multa por error de cálculo | Menor: impuestos del motor de Odoo | Mayor: el cálculo es propio |
| Dependencia | Del autor del módulo y de cada migración de Odoo | Solo de la API del PAC |

Conclusión FE: **es más fácil y menos riesgoso con Odoo** (módulo existente o herencia sobre un motor probado). La
diferencia de esfuerzo propio es pequeña; la de riesgo fiscal no. Elegir el PAC primero: su API manda en ambos
caminos. Mientras no exista FE, **no se puede facturar legalmente por encima de los umbrales**: es bloqueante para
producción en cualquiera de los tres caminos.

## 6. Recomendación

### 6.1 Veredicto

**Camino 3, híbrido por fases (strangler fig), con un final que probablemente NO es «todo nativo»:**
Odoo 19 Community **adelgazado** se queda como **back-office contable, fiscal y de inventario** (lo que tiene un motor
probado y una FE DGI disponible), y salen al borde de Cloudflare las piezas donde el borde gana de verdad: **sitio y
tienda** (rendimiento: hoy Lighthouse móvil 39–55 y LCP 8–11 s medido por r3-sitio-edge; HTML no cacheable),
**Brian** (eventos, costo, el producto que el dueño quiere) y, si hace falta que esté en línea con Odoo dormido,
**la app de socios**.

Por qué no los otros dos, en números:
- **Reconstruir todo (camino 2)**: $45–66 k en 24 meses frente a $12–19 k (1a) o $18–28 k (3); 1,1–1,6 años con una
  sola persona antes de la paridad; el riesgo contable y fiscal pasa a ser 100 % propio; y lo que ahorra en
  infraestructura frente a un VPS es ~$7–12/mes. Lo que el dueño quiere (barato y rápido) se consigue sin eso.
- **Solo adelgazar Odoo (camino 1)**: el más barato y es la base de la Fase 0, pero deja el sitio lento e
  incacheable dentro de Odoo y a Brian atado a la transacción HTTP de Odoo. Si el presupuesto de horas fuera el
  límite duro, 1a (VPS) es el plan B correcto.

Sobre «la plataforma más optimizada del mercado al menor costo»: la parte que el cliente ve (sitio, tienda, socios,
Brian) sí puede estar en lo más rápido y barato que existe (Workers + Static Assets + DO, ≈ $5/mes). La parte que el
cliente no ve (contabilidad, ITBMS, FE) gana más con «probado y aburrido» que con «nuestro».

### 6.2 Fases y criterios de salida

| Fase | Semanas (1 persona + Claude Code) | Qué | Criterio de salida (medible) |
|---|---|---|---|
| **0 · Odoo adelgazado a producción** | 6–10 | P0 del `INFORME_FINAL.md` (decisión ITBMS, cerrar RPC con `@api.private` + test, roles, legal, pimienta), quitar `crm`/SMS/IAP/UBL/tableros (§3.2), quitar el cron `*/10`, respaldos con restauración probada, hosting según r3-datos (VPS + Tunnel es el más barato medido hasta hoy) | 264+ tests verdes; test que falle ante método público con `sudo()` fuera de lista blanca; restauración ensayada < 1 h; módulos instalados medidos (antes 108) |
| **0b · FE DGI** (en paralelo) | 3–6 | Contador confirma obligación y fecha; elegir PAC; evaluar `l10n_pa_factura_electronica` v19 o escribir `l10n_pa_edi` | Factura tipo 00821 y una NC autorizadas en el ambiente de pruebas del PAC |
| **1 · Sitio y tienda al borde** | 4–6 | Odoo publica catálogo (JSON/HTML) a Static Assets/R2; carrito y checkout en el Worker; pedido → D1 `outbox` → Queue → `sale.order` en Odoo, idempotente | LCP móvil < 2,5 s y Lighthouse ≥ 90 (hoy 39–55); 0 pedidos perdidos o duplicados en 2 semanas de paralelo; Odoo sin tráfico anónimo en sus logs |
| **2 · Brian en el borde** | 4–6 | Diseño de r3-brian-agente/habilidades: agente en DO, herramientas que llaman a Odoo con identidad por persona | Evals de brian-evals verdes; costo por conversación medido y con tope; webhook de Telegram < 1 s |
| **3 · Socios al borde (opcional)** | 3–4 | Solo si Odoo va a dormir (Container en horario). Libro de puntos en un DO con el esquema §4; Odoo emite «factura pagada/anulada» | Reconciliación diaria borde vs recálculo desde facturas de Odoo = 0 diferencias durante 30 días |
| **4 · Punto de decisión (mes 12–18)** | — | Con datos reales de un año, decidir si seguir estrangulando (ventas → inventario) o parar | Ver §6.4 |

Total fases 0–3: ≈ 20–32 semanas (incluido en el TCO del camino 3).

### 6.3 Qué NO hacer

1. **No reconstruir contabilidad, facturación ni FE propias ahora.** Es donde un error es silencioso y caro, y Odoo ya lo resuelve.
2. **No empezar a facturar en serio sin decidir el camino.** Hoy hay 0 transacciones: migrar cuesta casi nada; desde la primera factura real cada cambio de sistema es una migración contable.
3. **No poner PostgreSQL dentro de un Container** (disco efímero) ni Odoo detrás de Hyperdrive (sin `LISTEN/NOTIFY`).
4. **No mantener Odoo 24/7 en Container + Neon** si se queda Odoo entero: es 4× el VPS por lo mismo.
5. **No cachear el HTML de Odoo en el borde** sin resolver cookie + CSRF (rompe el carrito: medido por r3-sitio-edge).
6. **No escribir el mismo dato en dos sistemas.** Cada dato tiene un solo dueño (catálogo/contabilidad = Odoo; carrito, Brian, socios-fase-3 = borde) y viaja por `outbox` + cola.
7. **No usar D1 «a pelo» para un libro** (leer-decidir-escribir sin serializar): libro de puntos o numeración en un DO, o escrituras condicionales + `UNIQUE`.
8. **No migrar a Odoo 20 todavía** (salió en sep-2026; esperar parches): Odoo 19 tiene soporte hasta ~sep-2028 (NO VERIFICADO en odoo.com).
9. **No ampliar Brian antes de cerrar B-02/B-03/B-04/S-09** (reproducidos por r3-brian-habilidades).

### 6.4 Cuándo SÍ reabrir la reconstrucción total (criterios objetivos)

Reconsiderar el camino 2 solo si, medido durante 12 meses, se cumple al menos uno:
- Migrar de versión de Odoo cuesta > 8 semanas o rompe > 30 % de los xpath/overrides propios.
- El tiempo que se pierde peleando con internos de Odoo supera 25 % del tiempo de desarrollo (llevar registro).
- Entra un segundo programador (cambia el denominador de semanas) o D'CASA abre sucursales con necesidades que Odoo Community no cubre.
- Aparece una obligación (fiscal o de negocio) que Odoo no puede cumplir y el código propio sí.
Y en ese caso, empezar por lo que el borde ya tenga (sitio, socios, Brian) y dejar la contabilidad para el final,
con el esquema de §4 y un período de cálculo en paralelo contra Odoo (mismos asientos, diferencias = 0).

## 7. Fuentes y verificación

Oficiales de Cloudflare (MCP `search_cloudflare_documentation`, consultado 2026-10-01):
- https://developers.cloudflare.com/workers/platform/pricing/ (Last updated 2026-08-28): Workers, D1, DO, Queues, R2, Workflows, Static Assets gratis.
- https://developers.cloudflare.com/d1/worker-api/d1-database/ (dateModified 2026-06-22): `batch()` transaccional.
- https://developers.cloudflare.com/d1/best-practices/read-replication/ : réplicas sin costo, Sessions API.
- https://developers.cloudflare.com/d1/observability/debug-d1/ : D1 corre sobre un Durable Object; errores de límite.
- https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/ : input/output gates, coalescencia, `transaction()`.
- https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/ : PITR 30 días con bookmarks.
- https://developers.cloudflare.com/durable-objects/concepts/what-are-durable-objects/ : hasta 10 GB por objeto.
- https://developers.cloudflare.com/durable-objects/platform/pricing/ : precios DO.
- https://developers.cloudflare.com/r2/pricing/ : R2 $0,015/GB-mes, 10 GB gratis.
- Límites de D1 (10 GB, Time Travel 30 días): el buscador del MCP no devuelve la página; cifra tomada de la entrada
  de r3-cf-plataforma (repo oficial `cloudflare-docs`). `developers.cloudflare.com` sigue bloqueado para WebFetch.

Otras (NO VERIFICADO en fuente primaria):
- FE Panamá: [Alegra](https://blog.alegra.com/panama/facturacion-electronica-panama/), [FacturaHQ](https://facturahq.cloud/es/facturacion-electronica-panama/), [DGI (no leída)](https://dgi.mef.gob.pa/_7facturaelectronica/R-Emisorfe).
- Módulo Odoo 19 FE Panamá: [apps.odoo.com](https://apps.odoo.com/apps/modules/19.0/l10n_pa_factura_electronica) (bloqueado por el proxy).
- Ciclo de soporte de Odoo: [odoo.com docs (no leída)](https://www.odoo.com/documentation/19.0/administration/standard_extended_support.html), [Wikipedia](https://en.wikipedia.org/wiki/Odoo).

Mediciones propias: consultas SELECT a `dcasa_test` (PostgreSQL 16 local), conteos de líneas con `find | wc -l`,
`validar_esquema.py` (SQLite 3.45.1) y `wrangler 4.143.0 d1 execute --local` en el scratchpad (sin cuenta).
Informes de otros agentes usados: r3-cf-plataforma (Containers, D1), r3-sitio-edge (Lighthouse, CSRF),
r3-brian-habilidades (PoC RPC), ronda 2 `cf-costos.md` (VPS).
