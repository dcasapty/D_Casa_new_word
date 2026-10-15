# Qué ve cada rol (permisos de la tienda)

Para la dueña: **quien vende no ve nómina ni la contabilidad de un jefe**, ni por el menú ni por un enlace.
Para quien programa: cómo está armado y cómo se comprueba. Reglas en
`addons/dcasa_base/security/dcasa_reglas_contables.xml`; pruebas en
`addons/dcasa_base/tests/test_permisos_contables.py` y `test_permisos_vendedora.py` (menús).

## En palabras sencillas

| | Vendedora / Cajero | Contador | Gerencia | Administrador |
|---|:---:|:---:|:---:|:---:|
| Ver el chatbot y las conversaciones, atender clientes | Sí | Sí | Sí | Sí |
| Crear y editar clientes | Sí | Sí | Sí | Sí |
| Ver productos (editar nombre y descripción) | Sí | Sí | Sí | Sí |
| Crear facturas y notas de crédito **de clientes**, buscarlas, imprimirlas y enviarlas | Sí | Sí | Sí | Sí |
| Registrar el cobro de una factura de cliente | Sí | Sí | Sí | Sí |
| Factura electrónica (DGI) | Sí | Sí | Sí | Sí |
| Facturas y notas **de proveedores** | **No** | Sí | Sí | Sí |
| Pagar a proveedores, devolver dinero a un cliente, pagos de nómina | **No** | Sí | Sí | Sí |
| Asientos contables varios (aquí se contabiliza la nómina) | **No** | Sí | Sí | Sí |
| Extractos y movimientos del banco, conciliación bancaria | **No** | Sí | Sí | Sí |
| Cuentas bancarias de los empleados | **No** | Sí | Sí | Sí |
| Reportes contables, rentabilidad por canal | **No** | Sí | Sí | Sí |
| Planillas, sueldos, liquidaciones | **No** | (según su grupo) | Sí | Sí |

**El Inicio de la vendedora** (pedido de la dueña, 2026-10-14) trae solo lo suyo: lo que **ella** vendió hoy y sus
cotizaciones abiertas. No ve lo que está por cobrarse, lo cobrado hoy, las barras ni los totales de la tienda; sus
herramientas son Productos, Facturas, Conversaciones, Nueva factura y Nuevo cliente. Lo mismo vale para **Ventas › Hoy ›
Ventas de hoy** y para el resumen de ventas de Brian: ella ve solo sus ventas; Gerencia, administradores y contabilidad
ven las de toda la tienda. Una venta cuenta cuando está facturada por completo y con la factura publicada (detalle en
`docs/OPERACION.md`, «Inicio»). La vendedora tampoco ve ninguna pantalla de Nómina: solo **Mis gastos por reembolsar**,
con sus propios gastos. (Ventas › Pedidos y Cotizaciones siguen mostrando todos los documentos: es el rol, para que
cualquiera atienda al cliente que vuelve.)

«Contador» es quien tiene Contabilidad en su ficha de usuario. Gerencia ya incluye Contabilidad y Nómina.
El lector contable (solo lectura) ve todo lo contable pero no cambia nada, igual que antes.

Lo que la vendedora **no** puede, por ejemplo: abrir la factura de un proveedor aunque conozca su número o su
enlace, ver cuánto se le pagó a un proveedor, ver el asiento de la nómina, ni ver los movimientos del banco.
Si lo intenta, Odoo le dice que no tiene permiso, o simplemente no le muestra nada.

**Devolver dinero a un cliente** (una nota de crédito pagada en efectivo o por Yappy) la registra Gerencia o
contabilidad. La vendedora sí crea y publica la nota de crédito.

## Cómo está armado (para quien programa)

### El problema de Odoo

Odoo da a quien tiene Facturación (`account.group_account_invoice`, que la Vendedora y el Cajero incluyen para
poder cobrar) reglas de registro con dominio `[(1, '=', 1)]` sobre `account.move` y `account.move.line`:
todos los asientos y todos los apuntes, sean de clientes, de proveedores o varios. Las reglas de grupo se
suman con «o», así que con una sola que abra todo, las otras no sirven. `account.payment`, los extractos
(`account.bank.statement`, `account.bank.statement.line`) y las conciliaciones no tenían reglas de grupo:
bastaba el permiso del modelo. Por el menú no se veían, pero por un enlace, `/json/2` o `call_kw` sí.

### Qué hace `dcasa_reglas_contables.xml`

1. **Estrecha** las reglas estándar que abrían todo a Facturación:
   `account.account_move_see_all` y `account.account_move_rule_group_invoice` (asientos),
   `account.account_move_line_see_all` y `account.account_move_line_rule_group_invoice` (apuntes),
   `account.account_analytic_line_rule_billing_user` (líneas analíticas),
   `account.ir_rule_res_partner_bank_billing_officers` (cuentas bancarias; sin las de empleados cuando Recursos
   Humanos está instalado) y `sale.account_invoice_report_rule_see_all` / `..._see_personal` (el análisis de
   facturas, que incluye compras y sus costos).
   Asientos: `out_invoice`, `out_refund`, `out_receipt` **o** el asiento de un cobro de cliente
   (`origin_payment_id.payment_type = 'inbound'`). Apuntes: los de esos asientos.
2. **Agrega reglas** de grupo para Facturación: pagos solo entrantes (`payment_type = 'inbound'`),
   extractos y movimientos bancarios ninguno (`id = 0`), conciliaciones solo si las dos puntas son apuntes que
   Facturación ya ve, y líneas analíticas solo de facturas de clientes (para todo empleado: con
   `dcasa_contabilidad` todos entran a la analítica).
3. **Devuelve todo** a quien tiene contabilidad: reglas `[(1, '=', 1)]` para `account.group_account_user` y
   `account.group_account_manager` (lectura y escritura), y para `account.group_account_readonly` solo lectura.
   El manager se pone aparte porque, sin `dcasa_contabilidad`, no implica al contador.
4. **No toca** las reglas globales de varias empresas (`*_comp_rule`), la de Compras sobre facturas de
   proveedor (`purchase.purchase_user_account_move_rule`) ni las de Ventas sobre facturas de clientes.

### Por qué `<function>` y no `<record>` (base nueva y base existente)

Las reglas estándar están en datos `noupdate="1"`. Odoo, al **actualizar** un módulo, no reescribe un
registro `noupdate` ni cuando otro módulo lo declara (`_load_records`: `update and noupdate` lo salta), y el
indicador `noupdate` de un `xmlid` ya existente tampoco cambia. Un `<record id="account.account_move_see_all">`
valdría para una base nueva y **no** para producción. Por eso las reglas estándar se cambian con
`<function model="ir.rule" name="write">` dentro de un bloque `noupdate="0"`: corre en cada instalación y en
cada actualización (el contenedor corre `-u` en cada despliegue con versión nueva), sin migración, y se puede
repetir sin efecto. Si algún día se vuelve a abrir una regla a mano en Ajustes técnicos, el siguiente
despliegue la vuelve a cerrar.

La regla de cuentas bancarias evalúa `'hr.employee' in user.env` al usarse, así que no depende del orden en que
se instalen `dcasa_base` y Recursos Humanos.

### Cómo se comprueba

- `test_permisos_contables.py`: la vendedora y el cajero facturan (también desde una orden de venta), cobran,
  concilian el cobro con la factura, hacen una nota de crédito, imprimen y preparan el envío; **no** leen,
  cuentan ni agrupan (`search`, `search_count`, `search_read`, `read_group`, `read`) ni escriben ni borran
  facturas de proveedor, notas de proveedor, asientos varios, pagos salientes, movimientos bancarios,
  conciliaciones de proveedor ni líneas analíticas de gastos, ni crean ninguno; Gerencia, contador, gerente
  contable y administrador ven y pueden hacer todo lo que su permiso de modelo permite (se compara contra
  `has_access`); el lector solo lee; las reglas sobreviven a una actualización (se vuelven a abrir a mano y se
  corre el archivo en modo `update`); y una exploración del código propio comprueba que ningún `sudo()` sobre
  asientos entregue algo que no sea de clientes.
- En una base existente: `odoo-bin -d <base> -u dcasa_base` y mirar *Ajustes › Técnico › Reglas de registro*.

### Campos que Odoo calcula con SQL directo (`models/campos_contables.py`)

Las reglas de registro no frenan un campo que Odoo calcula saltándose las reglas (`bypass_access`); solo lo frena
el grupo del campo, y esos campos traían «Facturación» (que la vendedora tiene para cobrar). Se les pide
contabilidad (`account.group_account_readonly` o `account.group_account_manager`):

- `res.partner.debit`: lo que la tienda le debe a cada proveedor.
- `account.journal.kanban_dashboard` y `kanban_dashboard_graph`: facturas de proveedor por pagar y retrasadas,
  y el saldo del banco y de la caja (las tarjetas del tablero de Facturación).

### Lo que queda abierto a propósito o fuera de este cambio

- **Devoluciones de dinero a un cliente** (pago saliente a un cliente): quedan para contabilidad o Gerencia. Si
  la dueña quiere que la vendedora las haga, hay que abrir `payment_type = 'outbound'` con
  `partner_type = 'customer'` en `regla_pagos_facturacion`; hoy se prefiere que no.
- **Órdenes de compra**: Odoo le da lectura a quien tiene Inventario (recibe mercancía contra la orden) y
  lectura y **escritura** a quien tiene Facturación (para enlazar facturas de proveedor), sin reglas de registro.
  No es contabilidad, pero es de jefe (precios de proveedor). No se cerró aquí porque recibir mercancía contra una
  orden lee la orden; si se quiere cerrar la escritura, es una regla de grupo con `perm_read = False` más una
  regla «todo» para Compras y contabilidad, probada con una recepción contra orden de compra.
- **Analítica con `dcasa_contabilidad`**: ese módulo hace a todo empleado miembro de
  `analytic.group_analytic_accounting`, que da lectura **y escritura** a cuentas, planes y modelos de
  distribución analítica. Las líneas con montos ya están protegidas aquí; la configuración conviene cerrarla en ese
  módulo (permiso solo para contabilidad).
- **Precios de proveedor de los productos** (`product.supplierinfo`) los lee todo empleado: se trata junto con los
  costos de los productos (ver `models/product.py`).
