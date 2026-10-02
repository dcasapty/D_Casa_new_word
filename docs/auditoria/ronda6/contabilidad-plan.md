# Ronda 6 — Contabilidad: brechas con Odoo Enterprise y plan por fases

Fecha: 2026-10-02. Pedido de la dueña: *«completa nuestra herramienta de contabilidad, supera a
Odoo Enterprise, crea el plan de implementación y construye algo mucho mejor y práctico»*.

Este documento (1) compara lo que da Enterprise con lo que hay en Odoo 19 Community y en
`dcasa_contabilidad`, verificado en el código; (2) prioriza por valor para una mueblería pequeña;
(3) deja construida la **fase 1** (ver §4) y (4) lista lo que **REQUIERE CONTADOR**.

Leyenda: **VERIFICADO** = leído en el código de este repo (`vendor/odoo` o `addons/`).
**ENTERPRISE** = módulo que no está en `vendor/odoo/addons` (Community); lo que hace se describe
por su nombre y función conocida, no por su código. Ninguna tasa, cuenta o regla fiscal de este
documento se inventa: donde hace falta criterio panameño dice **REQUIERE CONTADOR**.

---

## 1. Resumen

* **Lo grande ya lo tenía D'CASA** (rondas 1-5): reportes contables, conciliación bancaria propia,
  analítica, presupuestos y cheques, todo sobre los asientos de Community.
* **Faltaba lo que la dueña usa cada semana y el contador cada mes**: un resumen claro, comparar
  con el mes anterior, saber quién debe y desde cuándo, el flujo de efectivo, cerrar el mes para
  que nadie lo cambie, e importar el extracto del banco en cualquier formato. Eso es la fase 1 y
  **quedó construido y probado** (42 tests del módulo, 215 en total con Brian, factura y base).
* **Superamos a Enterprise en lo práctico**: todo en español claro, una sola pantalla de reportes
  con atajos de periodo, vista previa del extracto antes de importarlo, cierre de mes con lista de
  chequeo de datos reales y Brian respondiendo «¿cuánto gané este mes?» con las mismas cifras.
* **Lo que sigue (fase 2)**: cobranza con recordatorios por WhatsApp y estado de cuenta, paquete
  mensual para el contador, liquidación de ITBMS y activos fijos. Las dos últimas **requieren
  contador** antes de escribir una línea.
* **Hallazgo importante del plan contable `l10n_pa`** (VERIFICADO,
  `vendor/odoo/addons/l10n_pa/data/template/account.account-pa.csv`): el activo fijo (161-165) y el
  intangible (171-174) vienen con tipo **activo corriente**, los anticipos de clientes (212) como
  **cuenta por pagar** y los préstamos (222) como pasivo corriente. Con eso el balance muestra los
  muebles de la tienda como «activo corriente». Ver §5, puntos 1-3.

## 2. Qué se revisó (VERIFICADO)

| Pieza | Dónde | Qué hay |
|---|---|---|
| Fechas de bloqueo | `account/models/company.py:76-112, 552-605` | `fiscalyear_lock_date`, `tax_lock_date`, `sale_lock_date`, `purchase_lock_date`, `hard_lock_date` (irreversible) y validaciones (no bloquear con movimientos de banco sin conciliar ni borradores bajo el bloqueo definitivo). **Sin pantalla en Community**: ninguna vista los muestra (el asistente de bloqueo es de Enterprise). Excepciones: `account.lock_exception` (Community). |
| Reglas de conciliación | `account/models/account_reconcile_model.py` | Modelo `account.reconcile.model` con condiciones (diarios, monto, etiqueta, terceros) y líneas (cuenta, fijo/porcentaje/regex, impuestos). **Solo datos**: el motor que las aplica está en `account_accountant` (Enterprise). |
| Extractos | `account/models/account_bank_statement_line.py` | Sin importadores: CSV/OFX/CAMT son `account_bank_statement_import_*` (Enterprise). Sin campo de identificador único del banco. |
| Informes | `account/models/account_report.py` | El modelo `account.report` existe; el motor y la pantalla (`account_reports`) son Enterprise. `l10n_pa` no trae informe de impuestos. |
| ITBMS | `l10n_pa/data/template/account.tax-pa.csv` | ITBMS 7 % venta (`ITAX_19`) y compra (`OTAX_19`), **ambos a la cuenta 231** «ITBMS a pagar». |
| Diferidos | `account/wizard/account_automatic_entry_wizard.py`, `accrued_orders.py` | Community trae «cambiar periodo» (reparte un asiento) y devengos desde pedidos. Los diferidos automáticos por línea de factura son Enterprise. |
| Recurrentes y sellado | `account/models/account_move.py:294` (`auto_post` mensual/trimestral/anual), `account/wizard/account_secure_entries_wizard.py` | Community. No hace falta construirlos. |
| Seguimiento de cobros | `account/models/account_move_line.py:474` | Solo el campo `no_followup`; los niveles y cartas son `account_followup` (Enterprise). |
| Activos fijos | — | Nada en Community (`account_asset` es Enterprise). |
| D'CASA antes de esta ronda | `addons/dcasa_contabilidad` | Reportes (ER, balance, comprobación, mayor, ITBMS, analítica) con drill-down, XLSX y PDF; conciliación con sugerencias, parcial, automática segura y deshacer; importador CSV con detección de columnas; presupuestos; cheques; Brian con `reporte_contable`, `guia_cierre_mes`, conciliación. |

## 3. Tabla de brechas

Estado: ✅ hecho · 🟡 parcial · ⬜ falta. «Fase» = cuándo se cierra la brecha.

| # | Capacidad | Enterprise | Community 19 | D'CASA antes | D'CASA ahora | Brecha que queda | Fase |
|---|---|---|---|---|---|---|---|
| 1 | Resumen para la dueña (banco, cobrar, pagar, ITBMS, utilidad) | Tablero contable (Accounting dashboard) | Tablero de diarios | Tablero general (`dcasa_interfaz`) con «por cobrar» | ✅ **Resumen contable** con comparación y alertas, clic al detalle | — | 1 |
| 2 | Estado de resultados y balance con comparativos | `account_reports` | ⬜ | 🟡 sin comparativo | ✅ contra periodo anterior o año pasado, variación $ y %, drill-down, XLSX/PDF | Varias columnas (12 meses), filtro por canal analítico | 3 |
| 3 | Flujo de efectivo | `account_reports` | ⬜ | ⬜ | ✅ método indirecto, cuadra con bancos, comparativo, actividad configurable por cuenta | Método directo | 3 |
| 4 | Antigüedad de saldos CxC/CxP | `account_reports` (aged) | ⬜ | 🟡 lista de facturas abiertas | ✅ por tercero y tramo **a una fecha de corte** (pagos posteriores no cuentan), documentos, XLSX/PDF | Estado de cuenta por cliente (PDF) | 2 |
| 5 | Libro mayor y auxiliares | `account_reports` | Lista de apuntes | ✅ mayor | ✅ mayor | Auxiliar por tercero, libro diario | 2 |
| 6 | Conciliación bancaria | `account_accountant` | Solo modelos | ✅ pantalla propia | ✅ + **reglas** (automáticas o con un clic, mapeo de tercero) | Reglas con impuestos; depósitos de tarjeta por lote (bruto − comisión) | 2 |
| 7 | Importar extractos CSV/OFX/CAMT | `account_bank_statement_import_*` | ⬜ | 🟡 CSV autodetectado | ✅ CSV con **formatos por banco** y vista previa, OFX/QFX, CAMT.053, sin duplicar (FITID), aviso si el saldo no cuadra | Formatos reales de Banco General/Banistmo (falta un archivo de muestra) | 1→2 |
| 8 | Sincronización bancaria en línea | Online sync (cobertura por país) | ⬜ | ⬜ | ⬜ | No se hace: dependería de un agregador con cobertura en Panamá (no verificado) | — |
| 9 | Cierre de periodo y bloqueo | Asistente de bloqueo + cierre fiscal | Campos sin pantalla | 🟡 guía de Brian | ✅ **Cierre de mes**: lista de chequeo, bloqueo general y de ITBMS, reabrir con motivo, historial | Cierre anual (asiento de cierre, bloqueo definitivo) — REQUIERE CONTADOR | 3 |
| 10 | Activos fijos y depreciación | `account_asset` | ⬜ | ⬜ | ⬜ | Ficha de activo, depreciación lineal mensual, baja/venta — REQUIERE CONTADOR | 2 |
| 11 | Gastos/ingresos diferidos | `account_accountant` | Asistente «cambiar periodo» | ⬜ | ⬜ | Prepagados (seguro, alquiler) dentro de `dcasa_activos` | 2 |
| 12 | Presupuestos | `account_budget` | ⬜ | ✅ por cuenta y analítica | ✅ | Presupuesto mensual, alerta de sobre-ejecución, real vs presupuesto en el ER | 3 |
| 13 | Seguimiento de cobros | `account_followup` | Campo `no_followup` | 🟡 Brian «clientes que deben» | 🟡 antigüedad + Brian `antiguedad_saldos` | Niveles de recordatorio, mensaje de WhatsApp preparado (nunca enviado sin confirmación), estado de cuenta | 2 |
| 14 | ITBMS: resumen, liquidación y conciliación con la declaración | Informe fiscal + asiento de cierre de impuestos | Impuestos `l10n_pa` | ✅ resumen | ✅ + bloqueo de ITBMS al cerrar | Asiento de liquidación mensual, conciliación libros vs declaración, retenciones — REQUIERE CONTADOR | 2 |
| 15 | Paquete para el contador | Exportaciones de informes | ⬜ | XLSX por reporte | XLSX/PDF de todos los reportes | Un ZIP mensual (ER, balance, comprobación, mayor, auxiliares, ITBMS, cierre) | 2 |
| 16 | Asientos recurrentes, sellado (hash), notas de débito | Mismo que Community | ✅ (`auto_post`, `account.secure.entries.wizard`, `account_debit_note`) | ✅ | ✅ | Solo enseñar a usarlos | — |
| 17 | Lectura de facturas de proveedor (OCR) | `account_invoice_extract` (IAP) | ⬜ | Brian lee PDF/Excel | Brian lee PDF/Excel | Brian propone la factura de proveedor en borrador desde el PDF | 3 |
| 18 | Costo de ventas real | Valoración de inventario | `stock_account` (Community) | ⬜ productos sin costo | ⬜ | Cargar costos (ver auditoría `enterprise-gap.md` E-02): sin esto el margen sale 100 % | dependencia |
| 19 | Factura electrónica DGI | `l10n_pa_edi` (pv) | ⬜ | Pantalla «en desarrollo» | Lo hace otro agente (`dcasa_fe_pa`) | — | aparte |
| 20 | Nómina | `hr_payroll` | ⬜ | Plan | Plan | REQUIERE CONTADOR | aparte |

## 4. Plan por fases (lo práctico primero)

Esfuerzo: S ≤ 2 días · M 3-5 días · L > 5 días (una persona con este repo).

### Fase 1 — lo de todos los días (HECHA en esta ronda)

| Entregable | Esfuerzo | Criterio de aceptación (con su test) |
|---|---|---|
| **Resumen contable** (Facturación › Reportes contables › Resumen contable) | M | Dinero en cada banco/caja con lo que falta conciliar; «Te deben» y «Debes» con lo vencido; ITBMS del periodo; ventas y utilidad contra el periodo anterior; alertas que llevan al detalle. Las cifras son las mismas de los reportes (`test_resumen`). |
| **Comparativos** en ER, balance y flujo | S | Periodo anterior (por meses si empieza el día 1, fin de mes respetado) o mismo periodo del año pasado; filas que solo existen en el comparado aparecen con 0 (`test_periodo_comparado`, `test_estado_resultados_comparativo`). XLSX y PDF con columnas de variación (`test_exportar_comparativos_y_nuevos`). |
| **Flujo de efectivo** (indirecto) | M | Operación + inversión + financiamiento = variación del efectivo de los bancos («cuadra»); depreciación sumada y restada sin duplicar; actividad configurable por cuenta para el contador (`test_flujo_de_efectivo_cuadra_con_el_banco`, `test_flujo_con_depreciacion`, `test_flujo_actividad_elegida_por_el_contador`). |
| **Por cobrar / por pagar por antigüedad** | M | Por tercero y tramo (por vencer, 1-30, 31-60, 61-90, 91-120, +120) a una fecha de corte; un abono posterior al corte no cuenta; el total coincide con el saldo contable de la cuenta por cobrar (partida doble) (`test_antiguedad_por_cobrar`, `test_antiguedad_por_pagar`). |
| **Cierre de mes** con fecha de bloqueo | M | Lista de chequeo con datos reales (conciliación, borradores, ventas por facturar, comprobación y balance cuadran, cobros vencidos, ITBMS, meses anteriores); no cierra si falta algo que lo impide; solo la gerencia contable cierra; al cerrar nadie toca ese mes; reabrir pide motivo y deja historial (`test_cierre_de_mes_y_bloqueo`, `test_cierre_con_borradores_no_cierra`). |
| **Reglas de conciliación** | M | Usa `account.reconcile.model` de Community: condiciones de diario, monto, texto (contiene/no contiene/regex) y tercero; líneas fijo/porcentaje/regex; «Automático» se aplica al importar; manual se ofrece con un clic; regla de tercero asigna el cliente y deja que la factura se concilie sola (`test_regla_*`). |
| **Extractos CSV con formato, OFX y CAMT** | M | Formato por banco (columnas por nombre o número, filas de título, coma decimal, codificación Windows, cargos/abonos, signo invertido); vista previa antes de importar; OFX y CAMT con identificador del banco: re-importar no duplica aunque cambie la descripción; aviso si el saldo final del banco no coincide (`test_csv_con_filas_de_titulo_y_formato`, `test_leer_ofx_y_camt`, `test_importar_ofx_sin_duplicar`, `test_importar_camt`). |
| **Brian** | S | `resumen_contable` («¿cuánto gané este mes?», «¿cuánto ITBMS debo?»), `antiguedad_saldos` («¿quién me debe?»), `comparar_periodos`, `reporte_contable` con flujo de efectivo (lectura, grupo de contabilidad) y `cerrar_mes` (**sensible**: la gerencia contable confirma con un clic) (`dcasa_brian/tests/test_herramientas_contabilidad.py`). |
| Seguridad | — | Motores `@api.private`; la vendedora no llega ni por RPC (`test_seguridad_rpc`, `test_vendedora_no_usa_reglas_ni_cierre`); superficie RPC anotada en `dcasa_base/tests/test_superficie_rpc.py`. |

### Fase 2 — cobrar mejor y entregarle todo al contador (siguiente)

| Entregable | Esfuerzo | Criterio de aceptación |
|---|---|---|
| Estado de cuenta del cliente (PDF) y **recordatorios de cobro** por niveles | M | Desde «Por cobrar»: estado de cuenta con saldo, facturas y abonos; niveles (p. ej. al vencer, +15, +30 días — **días a definir por la dueña**) que preparan el mensaje de WhatsApp (CTA único, +507 6026-1919) y lo registran en el chatter; **nunca se envía sin confirmación**; Brian `recordatorio_de_cobro` sensible. |
| **Paquete mensual para el contador** | S | Un botón en el cierre de mes genera un ZIP con ER, balance, comprobación, mayor, auxiliar por tercero, ITBMS, por cobrar/pagar y la lista de chequeo, en XLSX y PDF. |
| Auxiliar por tercero y libro diario | S | Saldos inicial/final por cliente o proveedor con sus movimientos; diario por fecha y número; XLSX/PDF; cuadra con el mayor. |
| Liquidación mensual de ITBMS | M | Desde el resumen de ITBMS se arma un asiento **en borrador** que lleva el saldo a la cuenta por pagar a la DGI; cuentas configurables y **vacías por defecto**; conciliación del saldo de la 231 con lo declarado. **REQUIERE CONTADOR** (§5). |
| Activos fijos, depreciación y prepagados (`dcasa_activos`) | L | Ficha de activo (costo, fecha, vida útil, valor residual, cuentas), tabla de depreciación lineal, asientos mensuales por cron en borrador o publicados, baja/venta; prepagados que se reparten por meses. Vidas útiles y método **REQUIERE CONTADOR**. |
| Reglas con impuestos y depósitos de tarjeta por lote | M | Una regla con ITBMS calcula base e impuesto; un depósito del banco por ventas con tarjeta se explica como varios cobros menos la comisión (y la retención, si aplica). |
| Formatos reales de los bancos | S | Con un CSV real de Banco General y de Banistmo (pide la dueña en la banca en línea) se dejan sus formatos guardados y un test con esa muestra anonimizada. |

### Fase 3 — afinar

| Entregable | Esfuerzo | Criterio de aceptación |
|---|---|---|
| ER por varios periodos (12 meses en columnas) y por canal (analítica) | M | Una columna por mes y total; filtro por «Tienda física» / «Tienda en línea». |
| Presupuesto mensual vs real en el ER y alertas | M | Columna de presupuesto y % en el ER; aviso en el resumen cuando una cuenta pasa el 100 %. |
| Cierre anual | M | Asiento de cierre de resultados a la cuenta que diga el contador, bloqueo definitivo (`hard_lock_date`, irreversible) con doble confirmación. **REQUIERE CONTADOR**. |
| Factura de proveedor desde PDF con Brian | M | Brian lee el PDF y propone la factura en borrador (proveedor, líneas, ITBMS); una persona la publica. Coordinar con quien mejora Brian. |
| Método directo del flujo de efectivo | S | Cobros a clientes, pagos a proveedores, etc. desde las contrapartidas de los bancos. |

## 5. REQUIERE CONTADOR

Nada de esto se rellenó a ojo; el sistema lo deja configurable o vacío.

1. **Tipo de las cuentas de activo fijo e intangible** (161-165, 171-174 vienen como «activo
   corriente» en `l10n_pa`). Recomendación técnica: cambiarlas a «activo fijo» / «activo no
   corriente» para que el balance y el flujo las presenten bien. Decide el contador.
2. **Cuenta 212 «Anticipos de clientes»** viene como cuenta por pagar: aparecería en «Por pagar».
   ¿Se usará para los abonos de apartados (ronda 5) o se crea otra de pasivo corriente?
3. **Préstamos (222) y otras cuentas especiales en el flujo de efectivo**: elegir su actividad en
   el campo «Actividad en el flujo de efectivo» de la cuenta (operación/inversión/financiamiento).
4. **ITBMS en una sola cuenta (231)** para débito y crédito fiscal: ¿se separa el crédito fiscal?
   ¿Periodicidad y fecha de la declaración? ¿Cuentas del asiento de liquidación?
5. **Retenciones de ITBMS** (por ejemplo en cobros con tarjeta o si D'CASA es agente de retención):
   verificar si aplican; hoy no hay ninguna configurada.
6. **ITBMS de las comisiones bancarias**: ¿genera crédito fiscal? Define si las reglas de
   conciliación de comisiones llevan impuesto (fase 2).
7. **Depreciación**: método, vidas útiles y valor residual por clase de activo (fiscal y/o NIIF).
8. **Cierre anual**: cuenta del resultado del ejercicio (351-354 existen en el plan), reservas y
   cuándo aplicar el bloqueo definitivo (irreversible).
9. **Política de incobrables** (cuenta 125 «Previsión para incobrables»): cuándo y cuánto provisionar.
10. **Tramos de antigüedad**: se usan los estándar (30/60/90/120 días); confirmar si prefiere otros.
11. **Revisión del resumen de ITBMS contra la primera declaración real** antes de confiar en él.

## 6. Cómo se usa (para la dueña)

* **Facturación › Reportes contables › Resumen contable**: lo primero que se abre. Cada tarjeta
  lleva a su detalle.
* **Comparar**: en el estado de resultados, balance o flujo, «Comparar con» → periodo anterior o
  año pasado.
* **Bancos › Importar extracto**: sube el CSV, OFX o CAMT; revisa la vista previa; importa. Si un
  CSV no se reconoce, crea su formato en **Bancos › Formatos de extracto (CSV)** una sola vez.
* **Bancos › Reglas de conciliación**: para lo que se repite (comisiones, cargos de Yappy, un
  cliente que siempre paga por Yappy). «Automático» = se concilia sola al importar.
* **Cierre de mes**: crea el mes, revisa la lista, corrige lo pendiente con «Ver», y la gerencia
  pulsa «Cerrar mes». Marca «Bloquear también el ITBMS» cuando ya se declaró.
* **Brian**: «¿cuánto gané este mes?», «¿quién me debe?», «¿cuánto ITBMS tengo por pagar?»,
  «compara septiembre con agosto», «cierra septiembre» (pide confirmación).
