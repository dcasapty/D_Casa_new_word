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

