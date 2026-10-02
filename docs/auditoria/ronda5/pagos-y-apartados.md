# Ronda 5 — Pagos en línea, apartados y abonos

Fecha: 2026-10-02. Investigación, **sin cambios de código**. Regla de la casa: ninguna cifra
se da por buena si no sale de una página oficial con URL. Leyenda:

- **VERIFICADO-CÓDIGO**: leído en `vendor/odoo` de este repo (archivo:línea).
- **SEGÚN FUENTE**: lo dice la página citada (proveedor, banco, prensa), recogido vía buscador.
  El proxy de esta sesión bloqueó la descarga directa de `yappy.com.pa`, `tilopay.com`,
  `stripe.com` y `apps.odoo.com`, así que **ninguna tarifa quedó leída de primera mano**.
- **NO VERIFICADO**: hay que confirmarlo por escrito con el proveedor antes de decidir.

---

## 1. Pasarelas para un comercio panameño (2026)

D'CASA factura en USD, con RUC panameño y cuenta en banco local. Eso descarta de entrada a
quien exige entidad en EE. UU. u otro país.

| Proveedor | ¿Sirve a empresa PA? | Medios | Integración | Módulo Odoo 19 | Comisión (NO VERIFICADO salvo nota) |
|---|---|---|---|---|---|
| **Botón de Pago Yappy** (Banco General) | Sí; afiliación a Yappy Comercial desde Banca en Línea Comercial BG | Yappy (7 bancos según prensa) | API propia v2: JS en el frontend + 2 APIs (validar comercio, crear orden) + callback; SDK PHP/Node/.NET; ambiente UAT | **No hay oficial.** Había `payment_yappy` en apps.odoo.com (v18) y figura **despublicado** | 1 % + ITBMS por cobro, mínimo $0.02, débito diario (SEGÚN FUENTE: FAQ Yappy Comercial) |
| **Enlace de Pago BG / Botón de Pago BG** (Banco General) | Sí; requiere cuenta corriente/ahorro comercial BG, RUC en DGI, aviso de operación | Visa, Mastercard, 3DS 2.0 | Hosted Payment Page (redirección) o Checkout API; ambiente de pruebas | No hay | "Sin inscripción ni mensualidad, solo comisión por compra" (SEGÚN FUENTE); el % NO VERIFICADO |
| **Wompi** (Banistmo / Grupo Bancolombia) | Sí; Wompi es PSP de Banistmo en PA | Visa, Mastercard, Clave, Nequi | Widget/botón embebido, redirección, API, links de pago; modo de prueba al crear cuenta; depósito día hábil siguiente (SEGÚN FUENTE) | Los módulos que existen (Firefly-e `wompi_payment`, ecosire) son **para Wompi Colombia** (COP, PSE). Para PA habría que adaptar | Plan Gateway PA: tarifas negociadas con Banistmo (NO VERIFICADO) |
| **Tilopay** (fintech CR, en PA desde 2025) | Sí; facilitador de pagos, cualquier banco panameño, alta digital, procesa en ~48 h (SEGÚN FUENTE) | Visa/MC/Amex, Yappy, Clave, Tafi | Redirección/embebido, SDK, API, webhooks, **sandbox** | Terceros: "TILOPAY PAYMENT GATEWAY" (ABL Solutions, 17–19), "Tilopay Payment Connector" (BrowseInfo, 15–20), repo GitHub `victoreh24/odoo-payment-tilopay` (v19). **Sin auditar** | Tarjetas 3.75 % + $0.35; Yappy 2 % total (mín. $0.30) (SEGÚN FUENTE, página de Tilopay vía buscador, NO leída) |
| **PagueloFacil** | Sí; empresa formal con cuenta bancaria local | Tarjetas, Clave (SDK JS), enlace de pago, PagoCash | API REST + SDK; **sandbox** `sandbox.paguelofacil.com` | Terceros: "Paguelofacil Payment Provider" (Eduweb, hasta 19.0) y `tsl_payment_paguelofacil` (hasta 18.0). **Sin auditar** | 3.5 % + $0.50 local (+1 % internacional), retiro $1 (SEGÚN FUENTE: blogs de terceros, **no oficial**) |
| **BAC Credomatic e-commerce** (FAC/PowerTranz, Cardinal 3DS) | Sí, con afiliación de comercio BAC | Visa, MC, Amex | Plugin WooCommerce / API PowerTranz | No hay | Blog de terceros cita $75 alta, $50/mes, $0.18/tx (**NO VERIFICADO**, no oficial) |
| **Banesco PA e-commerce**, Banistmo adquirencia directa, Cybersource vía banco | Sí, vía el banco | Tarjetas | Según banco (Cybersource/PowerTranz) | No hay | NO VERIFICADO |
| **PayPal** | Sí: empresas panameñas pueden cobrar; retiro a banco local vía MetroBank/KIPO; límites de retiro empresa citados $2,000/día, $10,000/mes (SEGÚN FUENTE, paypal.com/pa y MetroBank) | PayPal, tarjetas vía PayPal | Redirección | **Oficial**: `vendor/odoo/addons/payment_paypal` (USD soportado, `payment_paypal/const.py:32`) | NO VERIFICADO. Útil sobre todo para clientes de fuera |
| **Stripe** | **No** para entidades panameñas. El propio Odoo no lista PA: `payment_stripe/const.py:83` (`SUPPORTED_COUNTRIES` sin `'PA'`). Las "soluciones" vistas exigen LLC + cuenta en EE. UU. | — | — | Oficial pero no aplicable | — |
| **dLocal** | Es *merchant of record* para empresas **extranjeras** que venden a Panamá (acepta Clave). No es para un comercio local | Tarjetas locales, Clave | API | No hay | NO VERIFICADO |
| **Nuvei** | NO VERIFICADO si contrata con comercios PA | Tarjetas | API | Oficial `payment_nuvei` (USD en `payment_nuvei/const.py:12`) | NO VERIFICADO |
| **Nequi Panamá** | Se cobra a través de Wompi | Nequi | Vía Wompi | — | — |

Notas comunes:

- **PCI**: con página alojada/redirección o iframe del proveedor (Yappy, Enlace BG HPP,
  Wompi widget, Tilopay redirect) D'CASA no toca el número de tarjeta → normalmente SAQ-A.
  Con "Checkout API" directo puede subir a SAQ A-EP. Confirmar con cada adquirente.
- **Recurrente / tokenización**: Tilopay y PagueloFacil anuncian cobros recurrentes;
  Yappy no aplica (lo aprueba el cliente en su app cada vez). Para abonos de apartado
  **no hace falta tokenizar**: cada abono es un pago nuevo que el cliente inicia.
- **Pago parcial**: ninguna pasarela lo impide; el monto lo fija Odoo al crear la
  transacción. La limitación está en Odoo (sección 2).
- **Borde Cloudflare**: los callbacks/webhooks (`/payment/<proveedor>/...`) pasan al origen;
  `edge/src/routing.ts:28` solo bloquea `/web/database`, `/jsonrpc`, `/xmlrpc`, `/json/2`,
  `/doc-bearer`, y nada fuera de estáticos se cachea (`routing.ts:93-98`). Sin cambios.
- **Odoo 19 oficial** (`ls vendor/odoo/addons/payment_*`): adyen, aps, asiapay, authorize,
  buckaroo, custom, demo, dpo, ecpay, flutterwave, iyzico, mercado_pago, mollie, nuvei,
  paymob, paypal, payu, razorpay, redsys, stripe, toss_payments, worldline, xendit.
  **Ninguno es panameño.** `payment_custom` (modo `wire_transfer`,
  `payment_custom/models/payment_provider.py:20-22`) sirve hoy mismo para "Yappy al
  número / ACH" con confirmación manual (la transacción queda *pending*).

Fuentes: [Yappy nueva integración](https://www.yappy.com.pa/comercial/desarrolladores/boton-de-pago-yappy-nueva-integracion/),
[Yappy Comercial FAQ](https://www.yappy.com.pa/comercial/preguntas-frecuentes/),
[Yappy requisitos](https://www.yappy.com.pa/comercial/requisitos/),
[T&C Yappy Comercial v3](https://yappyazipd9bfe9e9311.blob.core.windows.net/blobyappyazipd9bfe9e9311/wp-content/uploads/2025/08/Terminos%20y%20Condiciones%20de%20Yappy%20Comercial%20v3%204Ago25%202.pdf),
[Enlace de Pago BG](https://www.bgeneral.com/enlace-de-pago-bg/),
[Manual Enlace de Pago BG](https://www.bgeneral.com/wp-content/uploads/2023/10/Manual%20Enlace%20de%20Pago%20BG%202023.pdf),
[Wompi Banistmo](https://www.banistmo.com/pymes/adquirencia/wompi),
[Wompi PA plan Gateway](https://wompi.com/es/pa/planes-tarifas/plan-gateway),
[Reglamento comercios Wompi PA](https://wompi.com/assets/downloadble/reglamento-Comercios-Panama.pdf),
[Tilopay llega a Panamá](https://connect.tilopay.com/es-pa/tilopay-llega-a-panama-una-nueva-opcion-para-procesar-pagos-online/),
[Tilopay tarifas](https://tilopay.com/en/tarifas), [Tilopay Yappy](https://tilopay.com/yappy),
[Tilopay developers](https://tilopay.com/en/developers),
[PagueloFacil developers – Clave](https://developers.paguelofacil.com/guias/clave),
[PagueloFacil – enlace de pago](https://developers.paguelofacil.com/guias/enlace-de-pago),
[BAC comercio afiliado PA](https://www.baccredomatic.com/es-pa/pymes/comercio-afiliado),
[PayPal retiro Panamá](https://www.paypal.com/pa/webapps/mpp/withdraw-funds/impesa-metrobank),
[PayPal + Nequi/Banistmo](https://newsroom.latam.paypal-corp.com/alianzabanistmopanamaypaypal),
[dLocal Caribe/LATAM](https://www.dlocal.com/press-releases/dlocal-expands-emerging-markets-payments-platform-in-the-caribbean-latam/),
[apps.odoo.com PagueloFacil](https://apps.odoo.com/apps/modules/16.0/payment_paguelofacil),
[apps.odoo.com Tilopay](https://apps.odoo.com/apps/modules/17.0/payment_tilopay),
[apps.odoo.com payment_yappy (despublicado)](https://apps.odoo.com/apps/modules/18.0/payment_yappy),
[Banesco e-commerce](https://www.banesco.com.pa/empresas/servicios/ecommerce/).
Tarifas de PagueloFacil y BAC salen de blogs de terceros
([jootser](https://jootser.com/pasarelas-de-pago-para-e-commerce-en-panama/),
[pagos.blue](https://www.pagos.blue/pasarelas-de-pago/bac-credomatic/)): **no usar**.

---

## 2. Apartados y abonos en Odoo 19 Community

### 2.1 Lo que ya trae (VERIFICADO-CÓDIGO)

| Pieza | Dónde | Qué hace |
|---|---|---|
| Pago en línea para confirmar cotización | `sale/models/sale_order.py:117-126`, valor por empresa en `sale/models/res_company.py:17-18` y `sale_order.py:358-365` | `require_payment` + `prepayment_percent` (0–100 %). |
| Monto mínimo | `sale_order.py:2105-2118` | `amount_total * prepayment_percent`. |
| Confirmación al alcanzar el mínimo | `sale_order.py:2120-2131`; `sale/models/payment_transaction.py:108-131` | Cuando la suma de transacciones ≥ mínimo, confirma la orden (solo si 1 transacción ↔ 1 orden). |
| `amount_paid` | `sale_order.py:674-679` | **Solo suma `payment.transaction` en `authorized`/`done`.** Un abono en efectivo o Yappy en caja registrado como `account.payment` **no cuenta**. |
| Elegir anticipo o total en el portal | `sale/controllers/portal.py:220-233`, `:254-262`; plantilla `sale/views/sale_portal_templates.xml:442-460` | Modal con "anticipo" vs "monto total". |
| Rechazo de monto menor al mínimo | `sale/controllers/portal.py:142-145` | Error si `payment_amount` < anticipo y la orden no está confirmada. |
| Abonos posteriores | `sale_portal_templates.xml:190-196`; `sale_order.py:1856-1873` (`_get_default_payment_link_values`) | Tras confirmar, el botón "Pagar ahora" solo aparece si la URL trae `payment_amount` → **el cliente no elige cuánto abona**: el vendedor genera un *enlace de pago* (wizard `payment.link.wizard`) con el monto (máximo = saldo). |
| Aviso "Monto pagado" | `sale_portal_templates.xml:160-174` | Muestra `amount_paid` si 0 < pagado < total. |
| Factura de anticipo automática | `payment_transaction.py:90-97`, `:201-226`; `sale_order.py:2136-2149` | Con `sale.automatic_invoice` activo, cada pago parcial genera **una factura de anticipo** (`sale.advance.payment.inv`, método `fixed`) y el pago total genera la factura final que descuenta anticipos. |
| Cuenta de anticipos | `sale/models/res_company.py:50-56` (`downpayment_account_id`, admite `liability_current`); uso en `sale/wizard/sale_make_invoice_advance.py:209` | Permite mandar los anticipos a un **pasivo** en vez de ingreso. |
| Reserva de stock | `sale_stock/models/sale_order.py:213-215`; `stock/models/stock_picking.py:68-70` (`reservation_method` por defecto `at_confirm`) | Confirmar la orden crea el picking y reserva inventario. |
| Vencimiento de cotización | `sale_order.py:136` (`validity_date`), `:306`/`:759` (`is_expired`), `:1916-1937` (`_has_to_be_paid` exige no vencida) | Solo para cotizaciones; **una orden confirmada no vence**. |
| Facturas pagables en portal | `account_payment/controllers/portal.py:14-37`, `account_payment/models/account_move.py:55-67` | `/my/invoices/<id>` permite pagar el `amount_residual` (con `account_payment.enable_portal_payment`). |
| Tienda (carrito) | `website_sale/controllers/payment.py:63-68` | **Exige el total**: si el monto ≠ `amount_total` lanza "The cart has been updated". El carrito **no admite anticipo**; el anticipo solo existe en el flujo cotización → portal. |

### 2.2 Lo que falta para un apartado de verdad

1. **Saldo real**: `amount_paid` ignora pagos en caja. Un apartado mezcla web y tienda.
2. **Plan de abonos**: no hay calendario (fechas/montos), ni recordatorios.
3. **Vencimiento y abandono**: la orden confirmada no vence; nada libera el stock ni
   aplica la política de abonos al vencer.
4. **El cliente no elige el monto** del siguiente abono (depende del enlace del vendedor).
5. **Vista "Mis apartados"** con saldo, abonos y fecha límite: no existe.
6. **Puntos Socios**: `dcasa_socios/models/account_move.py:15-20` suma puntos al pagarse
   **cualquier** `out_invoice`, y `dcasa_compra.py:118-127` usa `amount_total_signed`.
   Con facturas de anticipo, **cada abono daría puntos** y el primer abono podría disparar
   el pago del referido (regla 4). Hay que decidir (y testear) que los puntos se ganen
   solo al liquidar el apartado, o aceptar el comportamiento actual (la anulación por nota
   de crédito ya existe, `account_move.py:44-56`). Decisión de Abrinay/dueña.
7. **Factura electrónica**: cada factura de anticipo sería un documento fiscal ante la DGI
   (ver §4); con muchos abonos se multiplican documentos. Contador.

### 2.3 Propuesta: módulo `dcasa_apartados` (diseño, no implementado)

**Principio**: reutilizar `sale.order` (no inventar otro documento de venta) y llevar los
abonos como `account.payment` de anticipo; el apartado es una "capa" sobre la orden.

Modelos:

- `sale.order` (herencia): `dcasa_es_apartado` (bool), `dcasa_apartado_vence` (date),
  `dcasa_apartado_estado` (selection: `activo`, `liquidado`, `vencido`, `cancelado`),
  `dcasa_abonado` (computado: transacciones `done` **+** pagos `account.payment` ligados),
  `dcasa_saldo` = total − abonado. **Sin columna de saldo almacenada editable**, igual que
  la regla del libro de Socios.
- `dcasa.apartado.cuota` (opcional, fase 2): orden, fecha, monto sugerido, pagado (computado).
- Parámetros en `res.company` (configurables, **sin valores por defecto inventados**):
  % mínimo de apartado, plazo máximo en días, días de gracia, política al vencer. Si están
  vacíos, el flujo no se habilita (mismo criterio que `puntos.json` = `PENDIENTE`).

Flujos:

1. **Crear**: vendedor (o el cliente desde la ficha web, fase 2) crea cotización con
   `require_payment=True` y `prepayment_percent` = % configurado; marca apartado.
2. **Primer abono**: en portal (`/my/orders/<id>`) o en caja. Al llegar al mínimo, Odoo
   ya confirma (`payment_transaction.py:108-131`) → **se reserva stock** por el picking
   normal (`at_confirm`). Recomendado: un tipo de operación/ubicación "Apartados" o al
   menos la etiqueta en el picking, para que el inventario disponible del sitio no venda
   el mismo mueble (website_sale_stock ya descuenta lo reservado: confirmar en test).
   Alternativa descartada: picking separado a ubicación interna "Apartados" — duplica
   movimientos y complica la entrega.
3. **Abonos siguientes**: ruta propia `/my/apartados/<id>/abonar` con monto libre entre
   mínimo de abono y saldo, que reutiliza `_get_payment_values`/`/my/orders/<id>/transaction`
   (`sale/controllers/portal.py:448`). En tienda: botón "Registrar abono" que crea
   `account.payment` de cliente ligado a la orden.
4. **Liquidar**: saldo = 0 → factura final (descuenta anticipos), entrega/retiro.
5. **Vencer**: cron diario; `dcasa_apartado_vence` + gracia superado → estado `vencido`,
   aviso por WhatsApp/correo; la **cancelación libera la reserva** (`action_cancel`).
   La devolución de abonos se resuelve según política aprobada por abogado (§4) mediante
   nota de crédito / pago de salida, **nunca borrando pagos**.

Contabilidad (**requiere al contador**): opción A — facturas de anticipo de Odoo con
`downpayment_account_id` en una cuenta de pasivo "Anticipos de clientes" (Odoo ya lo
soporta); opción B — `account.payment` sin factura a una cuenta de anticipos y una sola
factura al liquidar (menos documentos DGI, pero el ITBMS del anticipo debe tratarse como
diga el contador). Ambas deben validarse frente a la causación del ITBMS y la factura
electrónica.

Tests mínimos (`@tagged('post_install', '-at_install')`): confirmación al mínimo, saldo
con pago web + pago caja, reserva y liberación de stock al cancelar, cron de vencimiento,
puntos Socios solo al liquidar (si se decide así), sin cifras por defecto.

Esfuerzo estimado: **M** (sin calendario de cuotas), **L** con cuotas y recordatorios.

---

## 3. Portal del cliente (`/my`) en Community

Disponible (VERIFICADO-CÓDIGO):

- `/my`, `/my/home`, `/my/account`, `/my/addresses` — `portal/controllers/portal.py:184-219`.
- `/my/quotes`, `/my/orders`, `/my/orders/<id>` (+ `/accept`, `/decline`, `/transaction`,
  documentos adjuntos) — `sale/controllers/portal.py:106-448`.
- `/my/invoices`, `/my/invoices/<id>`, `/my/invoices/overdue` — `account/controllers/portal.py:84-153`,
  `account_payment/controllers/portal.py:53`.
- `/my/payment_method` (tarjetas guardadas, si el proveedor tokeniza) — `payment/controllers/portal.py:193`.
- Entregas visibles en la orden con `sale_stock`.

Qué personalizar para D'CASA:

- **Marca**: plantillas QWeb heredadas desde `website_dcasa` (Anton/Oswald/Inter, azul
  sobre blanco; botones amarillos solo sobre azul; español con tuteo). El portal hoy sale
  en estilo Odoo y con textos en inglés ("Pay Now", "Accept & Pay").
- **Mis apartados**: tarjeta en `/my/home` (vía `_prepare_home_portal_values`) y lista con
  saldo, abonos, vence el, botón "Abonar".
- **Saldo**: "Te falta $X" calculado de pagos reales, nunca escrito a mano.
- **Socios**: hoy Socios usa su propia sesión por celular + PIN (`dcasa_socios/controllers/main.py:62-276`,
  `/socios/cuenta`), no `res.users`. Enlace simple desde `/my` a `/socios/cuenta`; unificar
  sesiones es otro proyecto (regla 5: la llave es el celular).
- **CTA**: CLAUDE.md fija el CTA único "Escríbenos por WhatsApp". Activar pago en línea
  agrega un segundo CTA ("Pagar"/"Abonar"); **decisión de la dueña** si se permite solo
  dentro de `/my` (cliente que ya habló por WhatsApp y recibió su cotización).

---

## 4. Notas legales y fiscales (requieren contador/abogado)

- **ITBMS 7 %**: el catálogo maneja precios "+ ITBMS" (docs/CATALOGO.md) y hay dos impuestos
  de venta con nombres confusos (docs/AUDITORIA_UX.md #16, #41). El monto que se cobra en
  línea debe ser el total con ITBMS y la página debe mostrarlo claro antes de pagar.
  Confirmar con el contador cómo se causa el ITBMS en anticipos. **CONTADOR.**
- **Factura electrónica (SFEP / DGI)**: Ley 256 de 2021 y Decreto Ejecutivo 766 de 2020;
  la Resolución 201-6299 de 29-jul-2025 (vigente desde 1-ene-2026) limita el facturador
  gratuito a contribuyentes con ingresos brutos anuales hasta B/.36,000 y hasta 100
  documentos/mes; por encima se requiere **PAC** (SEGÚN FUENTE: blogs de Alegra/Softland,
  no se leyó la resolución). Docs/CONTABILIDAD.md ya registra que falta contratar PAC.
  Las ventas en línea no tienen régimen distinto: cada factura (incluidas las de anticipo)
  sería electrónica. **CONTADOR.**
- **Ley 45 de 2007 (protección al consumidor)**: según fuentes secundarias, el **art. 53
  ("custodia de bienes")** hace al proveedor responsable del bien que el consumidor aparta
  mediante abonos y le prohíbe sustituirlo por otro similar; cláusulas que limiten esa
  responsabilidad son nulas; no aplica a bienes **abandonados** (45 días calendario desde
  que se requirió al consumidor retirarlo). El art. 57 impide obligar a recibir notas de
  crédito cuando procede devolver dinero pagado en efectivo. **No hay derecho de retracto
  general** para compras en línea (solo ventas a domicilio, art. 71, 3 días hábiles) y la
  Ley 45 **no regula la devolución de abonos** cuando la compra no se concreta: existe un
  anteproyecto (dip. Ernesto Cedeño, 2026) para regularlo. Ley 51 de 2008 regula comercio
  y documentos electrónicos. Implicación de diseño: la política de vencimiento/devolución
  debe estar escrita, aceptada por el cliente al apartar y ser configurable (podría cambiar
  por ley). **ABOGADO.**

Fuentes: [Ley 45 (ACODECO, PDF)](https://www.acodeco.gob.pa/inicio/wp-content/uploads/2025/06/Ley45-31Oct2007_download.pdf),
[Gaceta Oficial Ley 45](https://www.gacetaoficial.gob.pa/storage/gacetas/2007/11/25914/7277.pdf),
[Asamblea: devolución de abonos](https://www.asamblea.gob.pa/Noticias/Legislativa/PROTECCION-EN-DEVOLUCION-DE-ABONOS-PARA-SEPARAR-O-RESERVAR-BIENES),
[Infobae 28-jul-2026](https://www.infobae.com/panama/2026/07/28/panama-anteproyecto-de-ley-pretende-garantizar-la-devolucion-del-dinero-a-los-consumidores-cuando-no-logren-finalizar-una-compra/),
[Telemetro](https://www.telemetro.com/nacionales/presentan-anteproyecto-regular-devolucion-abonos-separacion-bienes-n6086475),
[Metro Libre: retracto](https://www.metrolibre.com/economia/acodeco-el-derecho-al-retracto-no-esta-regulado-en-panama-JN4807812),
[ACODECO compras en línea](https://acodeco.gob.pa/educacion/2024/04/15/compras-en-linea/),
[Alegra: facturación electrónica 2026](https://blog.alegra.com/panama/facturacion-electronica-panama/),
[DGI](https://dgi.mef.gob.pa/New/New%20all/news.php?n=138).

---

## 5. Recomendación

**Shortlist**

1. **Yappy → Botón de Pago Yappy directo (Banco General)**. Es el medio que más usa el
   cliente panameño, la comisión publicada es la más baja vista (1 % + ITBMS, SEGÚN FUENTE),
   tiene ambiente de pruebas y API documentada. Contra: no hay módulo Odoo vivo; hay que
   escribir `payment_yappy` propio (proveedor `payment.provider` con JS del botón +
   validación del callback). Esfuerzo **M**.
2. **Tarjetas → Enlace de Pago BG con Hosted Payment Page** si la cuenta de D'CASA está
   en Banco General (mismo banco, mismo contrato, sin mensualidad SEGÚN FUENTE, 3DS 2.0,
   SAQ-A). Módulo propio tipo redirección: esfuerzo **M**. Si la cuenta está en Banistmo,
   la alternativa equivalente es **Wompi PA** (además trae Clave y Nequi).

**Plan B de un solo contrato**: **Tilopay** (tarjetas + Yappy + Clave, sandbox, módulos
Odoo 19 de terceros). Menos trabajo (**S–M**: auditar/adaptar un módulo existente), pero
comisión mayor (SEGÚN FUENTE 3.75 % + $0.35 en tarjeta, 2 % en Yappy) y un intermediario
más. Conviene si se quiere salir rápido y migrar después.

**Fase 0 sin integración (S)**: activar `payment_custom` como "Yappy / ACH — te
confirmamos por WhatsApp" para abonos desde el portal; el equipo marca la transacción
como hecha. Sirve para probar el flujo de apartados sin pasarela.

**Qué debe pedir la dueña**

- Banco General (Banca en Línea Comercial, perfil administrador): afiliación **Yappy
  Comercial** y habilitar **Botón de Pago Yappy**; credenciales de pruebas y producción.
- Banco General: solicitud **Enlace de Pago BG / Botón de Pago BG** — cuenta comercial,
  RUC/DV registrado en DGI, aviso de operación, sitio con políticas de entrega,
  cancelación y devolución publicadas, logos de marcas; **pedir por escrito**: % de
  comisión por marca, plazo de depósito, costo de contracargos, SAQ PCI exigido, si
  permiten montos parciales y reembolsos por API.
- Si aplica Wompi/Tilopay: mismas preguntas + contrato y reglamento de comercios.
- Contador: tratamiento contable e ITBMS de anticipos; PAC de factura electrónica.
- Abogado: texto de la política de apartado (plazo, abandono a 45 días según art. 53,
  devolución de abonos) y términos de compra en línea para `/terminos`.
