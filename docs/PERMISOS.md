# Qué ve cada rol (permisos de la tienda)

Para la dueña: **quien vende no ve nómina ni la contabilidad de un jefe**, ni por el menú ni por un enlace.
Para quien programa: cómo está armado y cómo se comprueba. Reglas en
`addons/dcasa_base/security/dcasa_reglas_contables.xml`; pruebas en
`addons/dcasa_base/tests/test_permisos_contables.py` y `test_permisos_vendedora.py` (menús).

## En palabras sencillas

| | Vendedora / Cajero | Contador | Gerencia | Administrador |
|---|:---:|:---:|:---:|:---:|
| Ver el chatbot y las conversaciones, atender clientes | Sí | Sí | Sí | Sí |
| En una conversación, cambiar a mano el cliente, quién atiende, las etiquetas, la pausa y su respuesta. El estado, la nota para el asistente y los seguimientos solo cambian con los botones (Atender, Devolver, Cerrar); a mano, solo el administrador del sistema | Sí | Sí | Sí | Sí |
| Crear y editar clientes | Sí | Sí | Sí | Sí |
| Ver productos (editar nombre y descripción) | Sí | Sí | Sí | Sí |
| Crear facturas y notas de crédito **de clientes**, buscarlas, imprimirlas y enviarlas | Sí | Sí | Sí | Sí |
| Registrar el cobro de una factura de cliente | Sí | Sí | Sí | Sí |
| Rebajar un precio: por línea, global o de importe fijo (se suman) | Hasta el tope de Ajustes de Ventas (10 % de fábrica) | Hasta el tope | **Sin tope** | **Sin tope** |
| Ajustar las existencias a mano (Inventario físico, Escáner › Contar) | **No** | **No** | Sí | Sí |
| Fusionar clientes repetidos (Socios › Configuración › Posibles duplicados) | **No** | **No** | Sí | Sí |
| Factura electrónica (DGI) | Sí | Sí | Sí | Sí |
| Facturas y notas **de proveedores** | **No** | Sí | Sí | Sí |
| Pagar a proveedores, devolver dinero a un cliente, pagos de nómina | **No** | Sí | Sí | Sí |
| Asientos contables varios (aquí se contabiliza la nómina) | **No** | Sí | Sí | Sí |
| Extractos y movimientos del banco, conciliación bancaria | **No** | Sí | Sí | Sí |
| Cuentas bancarias de los empleados | **No** | Sí | Sí | Sí |
| Reportes contables, rentabilidad por canal | **No** | Sí | Sí | Sí |
| Planillas, sueldos, liquidaciones | **No** | (según su grupo) | Sí | Sí |
| El menú **Empleados** (el Directorio de compañeros) | **No** | Sí | Sí | Sí |
| **Mis gastos por reembolsar** (registrar lo que pagó de su bolsillo; solo ve los suyos) | Sí | Sí | Sí | Sí |

**Quién cotiza, quién factura y quién cobra** (aclaración de la dueña, 2026-10-15): la vendedora **cotiza** (arma el
borrador); en caja, el personal **administrativo** hace la factura desde esa cotización y es **el único que cobra**. Es
la forma de trabajar, no un candado: el sistema todavía deja a la vendedora facturar y cobrar (la tabla de arriba),
porque quitárselo cambiaría permisos de datos y hay que decidirlo aparte con la dueña. Por eso el botón principal de su
Inicio es **Nueva cotización**; «Nueva factura» (suelta, sin cotización) y «Registrar cobro» solo salen en el Inicio
completo. Una factura hecha suelta no tiene pedido detrás: no cuenta en «Vendido hoy» ni tiene nota de entrega.

**El Inicio de la vendedora** (pedido de la dueña, 2026-10-14) trae solo lo suyo: lo que **ella** vendió hoy y sus
cotizaciones abiertas. No ve lo que está por cobrarse, lo cobrado hoy, las barras ni los totales de la tienda; sus
herramientas son Productos, Facturas, Conversaciones, Escáner, **Nueva cotización** (el botón principal: la vendedora arma el
borrador y la factura se hace en caja desde esa cotización) y Nuevo cliente. Lo mismo vale para **Ventas › Hoy ›
Ventas de hoy** y para el resumen de ventas de Brian: ella ve solo sus ventas; Gerencia, administradores y contabilidad
ven las de toda la tienda. Una venta cuenta cuando está facturada por completo y con la factura publicada (detalle en
`docs/OPERACION.md`, «Inicio»). La vendedora tampoco ve ninguna pantalla de Nómina: solo **Mis gastos por reembolsar**,
con sus propios gastos. Ya no ve tampoco la app **Empleados** (el Directorio de compañeros): la ven Gerencia,
administradores, contabilidad y quien administra al personal. Es solo de menú (`dcasa_equipo/data/menu_empleados_data.xml`
deja a `hr.menu_hr_root` con ese conjunto de grupos): los permisos de datos no cambian, los chats y las menciones siguen
mostrando los nombres, y «Mis gastos por reembolsar» es otra app que no depende de ese menú. (Ventas › Pedidos y Cotizaciones siguen mostrando todos los documentos: es el rol, para que
cualquiera atienda al cliente que vuelve.)

**Costos y ganancia** (decidido con la dueña, 2026-10-16): el costo de lo vendido y la ganancia (en el Inicio, en el menú
**Estadísticas › Mejor margen**, en las líneas de venta y en Brian) los ven solo **Gerencia y administradores**. La
Vendedora no los ve en ninguna pantalla y el servidor se los niega si los pide por la conexión de datos (esos campos
llevan el grupo). Brian tampoco le da a quien no es Gerencia la ganancia ni el costo del proveedor.

**Comparar y ventas por vendedora** (2026-10-17): el bloque **Comparar** del Inicio, el selector de **vendedora** y
«Por vendedora» son solo de **Gerencia y administradores** (los mismos que ven la ganancia). El servidor lo exige en
`dcasa.tablero.comparar_ventas` y rechaza que cualquier otro pida las ventas de otra persona (`ventas_del_periodo` con
un `vendedor` ajeno), también por Brian. La vendedora no ve el interruptor «Completadas / Con abonos»: su Inicio no cambió.

**Lo que todavía NO está cerrado (dicho con franqueza, revisión del 2026-10-16):** el campo «Costo» **del producto** es de
Odoo y lo ve cualquier empleado interno en la ficha del producto, y también algunos reportes de factura (margen) y el precio
del proveedor. No se tocó a ciegas porque Inventario, Compras y Contabilidad lo leen dentro de sus procesos y restringirlo
mal rompe entregas o recepciones. Queda como la siguiente tarea de seguridad (con pruebas de esos flujos); está en
[PRIORIDADES.md](PRIORIDADES.md). El menú Estadísticas completo (lo más vendido, mejor margen, lo que no se mueve) es de
Gerencia y administradores; «Lo más vendido» solo muestra ventas y unidades, no costos, y quien vende ya ve los pedidos.

**Tope de descuento (10 % para la Vendedora)** — cerrado en esta revisión: se mide siempre al crear la línea (aunque el precio
llegue por el contexto de la llamada), al cambiar de producto o de unidad de medida, y al tocar las banderas de anticipo o
combo; esas banderas ya no eximen por sí solas (un anticipo de Odoo no lleva producto; la marca de premio canjeado solo la
pone el sistema). Si Gerencia ya autorizó un descuento mayor en un pedido, la Vendedora puede seguir agregando notas, flete
o quitando líneas: se le bloquea solo lo que **empeora** el descuento, no lo que ya estaba.

**Existencias:** la cantidad (y lo reservado) de una existencia no la escribe a mano nadie que no sea Gerencia o el sistema,
con o sin el modo inventario. Recibir y entregar siguen igual (Odoo los corre por dentro con permisos del sistema).

**Fusión de contactos:** solo Gerencia, de a una persona; las fusiones masivas automáticas son del administrador del
sistema. Los puntos y el código de socio pasan completos a la ficha que queda y ésta deja una nota con lo que se le unió.

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
