# Qué ve cada rol (permisos de la tienda)

Para la dueña: **quien vende no ve nómina ni la contabilidad de un jefe**, ni por el menú ni por un enlace, y
**cada vendedora ve solo sus cotizaciones, pedidos, facturas, notas de crédito y cobros** (más lo que no tiene
vendedora, como los pedidos de la web); **Caja** y **Gerencia** ven todo. Esto último tiene un interruptor para volver
atrás (abajo). Y las **reglas contables de la gerencia** (17 oct, [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md)):
**el cobro solo en Caja** (la vendedora cotiza, confirma y factura, pero no cobra), el primer abono es **al menos la
mitad** del total (si es menos, Gerencia), y **anular, pasar a borrador, notas de crédito, devolver dinero y dejar saldo
a favor son solo de Gerencia**.
Para quien programa: cómo está armado y cómo se comprueba. Reglas en
`addons/dcasa_base/security/dcasa_reglas_contables.xml` y `dcasa_reglas_ventas.xml` (más las de Socios y de factura
electrónica); pruebas en `addons/dcasa_base/tests/test_permisos_contables.py`, `test_solo_lo_suyo.py` y
`test_permisos_vendedora.py` (menús).

Más abajo: [roles y grupos](#roles-y-grupos-mapa-completo) · [interruptores](#interruptores) ·
[reglas de Socios y Vendedores](#reglas-no-negociables-de-socios-y-vendedores) ·
[superficie RPC](#superficie-rpc-lista-blanca) · [privacidad](#privacidad) ·
[políticas del sitio](#políticas-del-sitio-dónde-viven-y-cómo-se-cambian).

## En palabras sencillas

| | Vendedora | Caja | Contador | Gerencia | Administrador |
|---|:---:|:---:|:---:|:---:|:---:|
| **Ver cotizaciones y pedidos** | **Los suyos** y los que no tienen vendedora* | Todos | (según su rol de Ventas) | Todos | Todos |
| **Ver facturas y notas de crédito de clientes** | **Las suyas** y las que no tienen vendedora* | Todas | Todas | Todas | Todas |
| **Ver cobros de clientes** | **Los suyos** (los que registró y los de sus facturas)* | Todos | Todos | Todos | Todos |
| Facturar la cotización de otra vendedora | **No*** | Sí | Sí | Sí | Sí |
| «Cobros de hoy (caja)» (Ventas › Hoy), la caja de toda la tienda | **No*** | Sí | Sí | Sí | Sí |
| Notas de entrega: despachar lo de cualquier vendedora (no lleva precios) | Sí | Sí | (según Inventario) | Sí | Sí |
| Oportunidades (CRM): siguen compartidas | Todas | Todas | — | Todas | Todas |
| Encender o apagar «Cada vendedora ve solo sus documentos» | No | No | No | Sí | Sí |
| Ver el chatbot y las conversaciones, atender clientes | Sí | Sí | Sí | Sí | Sí |
| En una conversación, cambiar a mano el cliente, quién atiende, las etiquetas, la pausa y su respuesta. El estado, la nota para el asistente y los seguimientos solo cambian con los botones (Atender, Devolver, Cerrar); a mano, solo el administrador del sistema | Sí | Sí | Sí | Sí | Sí |
| Crear y editar clientes | Sí | Sí | Sí | Sí | Sí |
| Ver productos (editar nombre y descripción) | Sí | Sí | Sí | Sí | Sí |
| Crear facturas **de clientes**, buscarlas, imprimirlas y enviarlas | Sí | Sí | Sí | Sí | Sí |
| **Registrar el cobro** de una factura de cliente (o un abono), un cobro suelto, o aplicarle un cobro que ya estaba («el cobro solo en Caja», 2026-10-17) | **No** (con el interruptor encendido o apagado) | Sí | Sí | Sí | Sí |
| Cobrar con **Tafi** o **Crediviva** (financieras: formas de pago en «Pagar») | No | Sí | Sí | Sí | Sí |
| Registrar un **primer abono menor a la mitad** del total | No | **No** | **No** | Sí | Sí |
| **Pasar a borrador o anular** una factura de cliente publicada | **No** | **No** | **No** | Sí | Sí |
| **Notas de crédito** de clientes; **devolverle dinero** a un cliente; cobrar de más dejándole **saldo a favor**; dar una factura por pagada con una diferencia | **No** | **No** | **No** | Sí | Sí |
| Rebajar un precio: por línea, global o de importe fijo (se suman) | Hasta el tope de Ajustes de Ventas (10 % de fábrica) | Hasta el tope de Ajustes de Ventas (10 % de fábrica) | Hasta el tope | **Sin tope** | **Sin tope** |
| Ajustar las existencias a mano (Inventario físico, Escáner › Contar) | **No** | **No** | **No** | Sí | Sí |
| Fusionar clientes repetidos (Socios › Configuración › Posibles duplicados) | **No** | **No** | **No** | Sí | Sí |
| Factura electrónica (DGI) | Sí | Sí | Sí | Sí | Sí |
| Facturas y notas **de proveedores** | **No** | **No** | Sí | Sí | Sí |
| Pagar a proveedores, pagos de nómina | **No** | **No** | Sí | Sí | Sí |
| Asientos contables varios (aquí se contabiliza la nómina) | **No** | **No** | Sí | Sí | Sí |
| Extractos y movimientos del banco, conciliación bancaria | **No** | **No** | Sí | Sí | Sí |
| Cuentas bancarias de los empleados | **No** | **No** | Sí | Sí | Sí |
| Reportes contables, rentabilidad por canal | **No** | **No** | Sí | Sí | Sí |
| Planillas, sueldos, liquidaciones | **No** | **No** | (según su grupo) | Sí | Sí |
| El menú **Empleados** (el Directorio de compañeros) | **No** | **No** | Sí | Sí | Sí |
| **Mis gastos por reembolsar** (registrar lo que pagó de su bolsillo; solo ve los suyos) | Sí | Sí | Sí | Sí | Sí |

\* Con **«Cada vendedora ve solo sus documentos» encendido**, que es como viene. Apagado, la Vendedora ve todo, como
antes del 2026-10-17 (la columna de Caja), pero **sigue sin cobrar**: Caja es su propio rol.

**Quién cotiza, quién factura y quién cobra** (aclaración de la dueña, 2026-10-15; rol Caja y reglas contables de la
gerencia desde el 2026-10-17): la vendedora **cotiza, confirma y factura** lo suyo; **cobra solo Caja** (el jefe
administrativo), además de Gerencia y contabilidad. Caja ve, factura y cobra las cotizaciones, pedidos, facturas y
cobros de clientes de toda la tienda, sin contabilidad, sin costos ni ganancia y con el tope de descuento de la
vendedora. **Anular o pasar a borrador** una factura publicada, las **notas de crédito**, **devolver dinero**, dejar
**saldo a favor** y aceptar un **primer abono menor a la mitad** son de **Gerencia** (Caja ya no las hace por su
cuenta). Lo que Caja factura desde la cotización de una vendedora **sigue siendo de esa vendedora** (su «Vendedor» no
cambia): ella lo ve, le cuenta para su meta y sale en «Ver mis ventas». El botón principal del Inicio de la vendedora
es **Nueva cotización**; «Registrar cobro» y «Caja de hoy» salen en el Inicio de Caja y en el completo. En la factura,
a la vendedora no le sale «Pagar»: le sale «El cobro de esta factura lo registra Caja». Una factura hecha suelta no
tiene pedido detrás: no cuenta en «Vendido hoy» ni tiene nota de entrega.

## Cada vendedora ve solo lo suyo (y cómo volver atrás)

Pedido de la dueña (2026-10-16: «los vendedores deberían solo poder ver las facturas que ellos hacen»; 2026-10-17:
«que esta opción se pueda habilitar o deshabilitar… si el día de mañana esto genera algún problema operativo se puede
retroceder fácilmente»).

- **Qué ve la vendedora:** sus cotizaciones, pedidos, facturas, notas de crédito y cobros, y los que **no tienen
  vendedora** (una cotización de Juan sin asignar), para que alguien los atienda. Cuando una vendedora confirma
  uno sin vendedora, pasa a ser suyo y las demás ya no lo ven; si lo confirma Caja, sigue sin vendedora (lo ven todas y
  no cuenta para la meta de nadie). Lo que ella crea queda siempre a su nombre, aunque la ficha del cliente diga otra
  vendedora. **Cobrar:** desde el 2026-10-17 la vendedora **no cobra** (decisión de la gerencia A5: el cobro solo en
  Caja); sigue facturando. No se le quitó «Facturación» (la necesita para facturar): el servidor le niega cada camino
  de cobro (`dcasa_base/models/cobros.py`).
- **Los pedidos de la web entran sin vendedora** (decisión de la dueña, 2026-10-17; `website_dcasa/models/pedido_web.py`):
  los ven todas y **la vendedora que lo confirma se lo queda** (con el interruptor encendido o apagado); si lo confirma
  Caja o Gerencia, o la tienda sola (pago en línea), sigue sin vendedora. Ni el «Vendedor» del sitio web ni la vendedora
  de la ficha del cliente se lo ponen (antes Odoo se lo daba al administrador y las vendedoras no lo veían). El
  «Vendedor» del sitio (*Ajustes › Sitio web*) queda vacío (la migración 19.0.1.15.0 lo vacía una vez); si un
  administrador lo vuelve a poner, los pedidos web van a esa persona, como en Odoo. El **vendedor del programa** (link
  `/v/CÓDIGO`, `sale.order.dcasa_vendedor_id`) es otra cosa y no cambia: el carrito lo anota, pasa a la factura y su
  comisión sigue igual. El aviso de un **apartado web por vencer** sin vendedora le llega a **Caja** (si nadie tiene
  Caja, a Gerencia).
- **Qué ven Caja y Gerencia:** todo.
- **Lo que no cambia:** las notas de entrega (todas despachan), las oportunidades del CRM (compartidas), la
  contabilidad (contador y lector ven todo, como antes) y Juan.
- **Dar el rol Caja** (no se le pone solo a nadie): *Ajustes › Usuarios y compañías › Usuarios* › abrir a la persona
  que cobra › en **D'CASA** elegir **Caja** › Guardar. Vale al momento. También con Brian (un administrador): «ponle el
  rol cajero a …». La Guía lo explica en «Darle acceso al sistema a una persona del equipo».
- **El interruptor «Cada vendedora ve solo sus documentos»** (viene **encendido**): Gerencia lo tiene en *Ventas ›
  Configuración › Permisos de las vendedoras*; los administradores, también en *Ajustes › Ventas*; y Brian
  («que las vendedoras vuelvan a ver todo»). **Apagado, todas las vendedoras vuelven a ver todo como antes**, al
  momento, sin tocar la ficha de nadie; se vuelve a encender igual. La Guía: «Elegir si cada vendedora ve solo sus
  documentos».

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
mostrando los nombres, y «Mis gastos por reembolsar» es otra app que no depende de ese menú.

**Costos y ganancia** (decidido con la dueña, 2026-10-16): el costo de lo vendido y la ganancia (en el Inicio, en el menú
**Estadísticas › Mejor margen**, en las líneas de venta y en Brian) los ven solo **Gerencia y administradores**. La
Vendedora no los ve en ninguna pantalla y el servidor se los niega si los pide por la conexión de datos (esos campos
llevan el grupo). Brian tampoco le da a quien no es Gerencia la ganancia ni el costo del proveedor.

**Comparar y ventas por vendedora** (2026-10-17): el bloque **Comparar** del Inicio, el selector de **vendedora** y
«Por vendedora» son solo de **Gerencia y administradores** (los mismos que ven la ganancia). El servidor lo exige en
`dcasa.tablero.comparar_ventas` y rechaza que cualquier otro pida las ventas de otra persona (`ventas_del_periodo` o
`grafica_de_ventas` con un `vendedor` ajeno), también por Brian. La vendedora no ve el interruptor «Facturado · Con abonos
· Completadas» ni los íconos ⓘ, y la gráfica de la tienda se le niega en el servidor: su Inicio no cambió (sigue con sus
pedidos facturados por completo). Las facturas del Inicio de Gerencia se suman con `sudo` siempre filtrado a facturas y
notas de crédito de cliente; la lista que abre cada cifra la ve cada quien con sus permisos.

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

**Devolver dinero a un cliente** (una nota de crédito pagada en efectivo o por Yappy) y la **nota de crédito** misma
las hace solo **Gerencia** (o un administrador) desde el 2026-10-17; la vendedora, Caja y el contador ya no.

## Cómo está armado (para quien programa)

### El problema de Odoo

Odoo da a quien tiene Facturación (`account.group_account_invoice`, que la Vendedora y la Caja incluyen para
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
   Asientos (desde el 2026-10-16, **lo suyo**): su factura, nota o recibo de cliente (`invoice_user_id` = ella, o
   sin vendedora) **o** el asiento de su cobro de cliente (`origin_payment_id`: entrante y registrado por ella o de
   sus facturas). Apuntes: los de esos asientos. Analítica: la de sus facturas de clientes.
2. **Agrega reglas** de grupo para Facturación: sus pagos entrantes (los que registró, `create_uid`, o los de sus
   facturas, `invoice_ids`), extractos y movimientos bancarios ninguno (`id = 0`), conciliaciones solo si las dos
   puntas son apuntes que ella ya ve, y líneas analíticas solo de sus facturas de clientes (para todo empleado: con
   `dcasa_contabilidad` todos entran a la analítica).
2b. **«Toda la tienda, solo de clientes»** para `sales_team.group_sale_salesman_all_leads` (Caja, Gerencia y, con el
   interruptor apagado, la Vendedora) y `account.group_account_readonly`: asientos, apuntes, cobros, conciliaciones
   y analítica de clientes de toda la tienda, el mismo dominio que Facturación tenía antes del 2026-10-16.
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

- `test_permisos_contables.py`: la vendedora y el cajero facturan (también desde una orden de venta), ven el cobro
  que registra Caja y su conciliación con la factura, imprimen y preparan el envío (la nota de crédito, solo Gerencia:
  `test_reglas_gerencia.py`); **no** leen,
  cuentan ni agrupan (`search`, `search_count`, `search_read`, `read_group`, `read`) ni escriben ni borran
  facturas de proveedor, notas de proveedor, asientos varios, pagos salientes, movimientos bancarios,
  conciliaciones de proveedor ni líneas analíticas de gastos, ni crean ninguno; Gerencia, contador, gerente
  contable y administrador ven y pueden hacer todo lo que su permiso de modelo permite (se compara contra
  `has_access`); el lector solo lee; las reglas sobreviven a una actualización (se vuelven a abrir a mano y se
  corre el archivo en modo `update`); y una exploración del código propio comprueba que ningún `sudo()` sobre
  asientos entregue algo que no sea de clientes.
- En una base existente: `odoo-bin -d <base> -u dcasa_base` y mirar *Ajustes › Técnico › Reglas de registro*.

### «Solo lo suyo», Caja y el interruptor (2026-10-16 y 2026-10-17)

- **Roles** (`security/dcasa_roles.xml`): la Vendedora implica «Ventas: solo sus documentos»
  (`sales_team.group_sale_salesman`), Facturación e Inventario. **Caja** (`dcasa_base.group_caja`) = Vendedora +
  «Ventas: todos los documentos» (`sales_team.group_sale_salesman_all_leads`), sin contabilidad, costos ni descuento
  sin tope; Gerencia incluye Caja. Un solo selector «D'CASA»: Vendedora → Caja → Gerencia. Caja no se asigna sola.
- **Qué es «suyo»:** pedidos y cotizaciones, `sale.order.user_id`; facturas, notas y recibos, `account.move.invoice_user_id`
  (nunca quién lo creó: Caja crea la factura desde la cotización de la vendedora); cobros, los que registró o los de sus
  facturas. Lo sin vendedora lo ven todas (lo que hace Odoo).
- **Reglas:** Odoo ya cierra pedidos, líneas, análisis de ventas y de facturas a «solo sus documentos». Las facturas,
  cobros, apuntes, conciliaciones y analítica las cierra `dcasa_reglas_contables.xml`; `dcasa_reglas_ventas.xml` deja
  las oportunidades compartidas y estrecha la regla de `sale_stock` que le dejaba a Inventario leer todas las líneas de
  pedido; `dcasa_socios/security/dcasa_reglas_socios.xml` (compras con puntos y comisiones) y
  `dcasa_fe_pa/security/dcasa_reglas_fe.xml` (documento electrónico e intentos) hacen lo mismo en sus módulos.
- **Dueña del documento** (`models/sale_order.py`, `models/account_move.py`): quien solo ve lo suyo
  (`res.users._dcasa_solo_lo_suyo`) queda siempre como vendedora de lo que crea y de lo sin vendedora que confirma. Si
  no, Odoo pondría a la vendedora de la ficha del cliente (o la de `default_user_id`) y la creación fallaría porque ella
  no podría ver lo que acaba de crear. Juan, la web y los procesos automáticos corren con `sudo` y no cambian.
- **Lo que se leía con `sudo`:** la ficha y los documentos para adjuntar de Conversaciones ahora buscan como quien mira.
  Brian corre como el usuario y agrega `alcance` a sus cifras de facturas (docs/BRIAN.md).
- **El interruptor** (`models/res_users.py`, `models/solo_lo_suyo.py`, `views/solo_lo_suyo_views.xml`): su estado ES
  si el rol Vendedora implica «Ventas: todos los documentos». Encendido no la implica; apagado, sí, y todas las reglas
  «toda la tienda» le vuelven a aplicar a la Vendedora (es lo de antes, sin tocar ninguna ficha: Odoo 19 calcula los
  grupos implícitos al vuelo). `_dcasa_poner_restriccion` exige Gerencia o administrador **en el servidor**.
  `dcasa_roles.xml` **no nombra** esa implicación (ni `(4, …)` ni `(3, …)`): si la nombrara, cada despliegue (`-u`)
  movería el interruptor. La base de antes (que la tenía) la pierde **una vez** en la migración `19.0.1.8.0`, que
  además le quita «todos los documentos» puesto a mano a la Vendedora sin Caja, Ventas administrador ni lectura
  contable, y avisa en el registro si nadie tiene Caja. El menú «Cobros de hoy (caja)» cuelga de «todos los
  documentos», así que también vuelve a la Vendedora con el interruptor apagado.
- **Pruebas** (`tests/test_solo_lo_suyo.py`): la Vendedora A no encuentra nada de B por `search`, `search_count`,
  `search_read`, `_read_group`, `name_search`, leer por número, `_render_qweb_pdf`, `/report/pdf`, `/web/content`
  (adjunto) ni `mail.message`; sí ve lo suyo y lo sin vendedora; confirmar lo sin vendedora es tomarlo; la ficha que
  dice B no traba a A; A despacha lo de B; Caja ve, factura, cobra e imprime todo y la vendedora no cambia (la nota de
  crédito la hace Gerencia desde el 2026-10-17); Gerencia, contador y lector ven todo; las dos posiciones del
  interruptor, el ida y vuelta (sin cambiar el grupo de ninguna persona), que guardar otro ajuste o desplegar no lo
  mueve, y que la Vendedora y Caja no pueden
  moverlo; la migración. Además en `dcasa_socios`, `dcasa_fe_pa`, `dcasa_conversaciones`, `dcasa_interfaz`,
  `dcasa_invoice`, `dcasa_brian` y `dcasa_nomina` (`test_solo_lo_suyo.py` o junto a sus pruebas).
- **Lo que queda fuera a propósito:** las notas de entrega (todas despachan; no llevan precios), las transacciones de
  pago en línea (Odoo se las abre a todo el que vende; casi todas son de la web), los enlaces del portal con `access_token` (son del cliente)
  y las facturas cargadas del sistema anterior (`dcasa_migracion` no les pone vendedora: Odoo les pone la de la ficha
  del cliente o a quien hizo la carga, así que en general las ven Caja y Gerencia; comprobado en una base de prueba
  migrada desde `3b678a6`, no con la de producción).
- **Lo que una vendedora todavía alcanza a ver de lo de otra, porque se comparte a propósito** (revisión adversarial,
  2026-10-17; decisión de la dueña si alguno molesta): el número del pedido y de la factura en la **nota de entrega**
  (también en la fácil de leer, que lee la factura con `sudo` para que cualquiera la imprima); lo que se habló y los
  PDF que se le mandaron al cliente en **Conversaciones** (las conversaciones son de todo el equipo); las notas
  automáticas de la **oportunidad** del CRM («se envió S0…», «se pagó la factura INV/…»); los **puntos de Socios** del
  cliente y los del **programa de vendedores** (cada movimiento dice «Compra INV/…» y los puntos, que siguen al monto);
  el aviso **«Parece repetido»** (da el número del otro pedido del mismo cliente, día y total); y el **«Total por
  cobrar»** del cliente y el «Facturado este mes» del equipo de ventas (cifras de Odoo que suman toda la tienda; no
  salen en las pantallas de la vendedora, solo pidiéndolas por la conexión de datos).
- **Cifras que se suman por SQL** (no pasan por las reglas): «Ventas atribuidas» del Resumen de Conversaciones se acota a
  mano a lo suyo para quien ve solo lo suyo (`dcasa.juan.panel._ventas_atribuidas`, revisión adversarial 2026-10-17).
  Cualquier suma nueva por SQL de facturas o pedidos tiene que hacer lo mismo.

### Reglas contables de la gerencia (2026-10-17)

Decisiones A3, A5, A6, A7 y C1 de [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md). Todo se comprueba **en el
servidor** (esconder el botón no basta); el superusuario y lo que corre con `sudo` (la web, Juan, el cron, la carga del
sistema anterior) no cambian; lo de proveedores tampoco.

- **Quién cobra** (`dcasa_base/models/cobros.py`, `res.users._dcasa_puede_cobrar`): Caja (`dcasa_base.group_caja`,
  que Gerencia incluye), contabilidad (`account.group_account_user` o `account.group_account_manager`) y
  administradores (`base.group_system`). No es «todos los documentos»: con el interruptor apagado la Vendedora ve todo
  pero sigue sin cobrar. Caminos cerrados: el asistente «Pagar» (`account.payment.register._create_payments`, que usan
  también Brian e integraciones), el botón «Pagar» de la factura y de la lista (`account.move.line.action_register_payment`),
  crear, publicar, cambiar, pasar a borrador, cancelar o borrar un `account.payment` de cliente, aplicar o quitar un
  cobro desde la factura (`js_assign_outstanding_line`, `js_remove_outstanding_partial`) y cruzar a mano lo que debe un
  cliente (`account.move.line.reconcile`, `account.partial.reconcile` crear y borrar, que es lo que hace `remove_move_reconcile`). En la
  pantalla: el campo `dcasa_puede_cobrar` esconde «Pagar» y muestra «El cobro de esta factura lo registra Caja»; el
  Inicio no le da «Registrar cobro»; Brian no le ofrece `registrar_pago` (grupos «alguno de», `registro.py`) y su
  prompt le dice que los cobros los registra Caja; la Guía no le muestra «Registrar el cobro», «Registrar un abono» ni
  «Cobrar una compra que financia Tafi o Crediviva» (tienen `grupos`).
- **Solo Gerencia** (`res.users._dcasa_es_gerencia`: `dcasa_base.group_gerencia` o `base.group_system`):
  `button_draft`, `button_cancel` y `write({'state': 'draft'|'cancel'})` de una factura, nota o recibo de cliente
  publicado; `action_reverse` y crear o publicar (`_post`) una nota de crédito de cliente (también la que deja en
  borrador una devolución de un pedido); un `account.payment` saliente a un cliente (y «Pagar» una nota de crédito); en
  el asistente, cobrar de más dejando la diferencia abierta (saldo a favor) o «marcar como pagada» con una diferencia.
  El contador sin Gerencia queda fuera de estas (la decisión dice «solo Gerencia»); está en
  [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md), punto 24, por si la gerencia quiere otra cosa.
- **Lo que solo daría error no se ofrece** (2026-10-18; `dcasa_base/views/account_move_views.xml`, campos
  `dcasa_es_gerencia` y `dcasa_puede_cobrar`): en una factura, nota o recibo de cliente publicado, a quien no es Gerencia
  (Caja y el contador incluidos) no le salen «Nota de crédito» ni «Restablecer a borrador» (una cancelada sí vuelve a
  borrador, como deja el servidor); en una nota, «Pagar» solo a Gerencia; «Créditos pendientes: Agregar» solo a quien
  cobra. Del menú «Acción» salen «Pagar», «Revertir» y «Cambiar a factura/nota de crédito» para quien no es Gerencia,
  contabilidad ni administrador (también el botón «Revertir» de un asiento). En los pagos de clientes, «Publicar»,
  «Restablecer a borrador» y «Cancelar» solo a quien puede (`account.payment.dcasa_puede_tocar`) y la Vendedora no ve
  «Nuevo» (`account.payment.get_view`); en el globito de un pago de la factura, «Desconciliar» solo a quien cobra
  (`static/src/xml/pagos.xml`). En «Pagar», a quien no es Gerencia no se le ofrece qué hacer con la diferencia (queda
  abierta) y, si cobra de más, el asistente lo avisa antes («Estás cobrando más de lo que falta…»). La Guía muestra
  «Borrar una factura de prueba que ya dio puntos» (pasa por «Restablecer a borrador») solo a Gerencia. El servidor lo
  sigue negando igual por RPC o Brian (`TestBotonesSoloAQuienPuede`).
- **Pagos en línea** (si algún día la tienda cobra en línea): al publicar la factura de un pedido ya pagado en la web,
  Odoo cruza solo ese pago con la factura; eso no es «registrar un cobro» y se deja pasar
  (`pago_en_linea_de_su_factura`). Con «ver solo lo suyo» encendido la vendedora no ve ese pago: la factura se publica
  por cobrar y Caja le aplica el cobro desde la factura (comprobado en una base de prueba).
- **Primer abono** (`dcasa_invoice/models/primer_abono.py`): si la factura de cliente no tiene pagos (una nota de
  crédito aplicada no cuenta), el primer pago del asistente es al menos `ANTICIPO_MINIMO` (la mitad) de su total, salvo
  que la complete; si no, `UserError` con «El primer abono debe ser de al menos la mitad: $X. Si es menos, lo registra
  Gerencia.» (Gerencia y administradores pasan). Un pago agrupado de varias facturas se revisa al final y se deshace
  entero si alguna quedó por debajo. El asistente lo avisa antes (`dcasa_aviso_primer_abono`). La conciliación bancaria
  y aplicar un cobro que ya estaba no se frenan: los ganchos de conciliación (`_reconcile_pre_hook`/`_post_hook`) dejan
  una nota en la factura («Primer abono de $X: es menos de la mitad… Que Gerencia lo revise» o «Lo autorizó y lo
  registró … (Gerencia)»). Lo cargado del sistema anterior y lo que corre con `sudo` no deja notas.
- **Vencimiento del abono**: `_dcasa_estado_abono` suma `dcasa_invoice.abono_dias` días continuos (30) al primer
  abono; de ahí leen el papel, las Condiciones, «Mi cuenta», los correos y Brian (`ver_factura`, `facturas_pendientes`).
- **Tafi y Crediviva** (`dcasa_base.crear_diarios_financiamiento`): diarios de banco `TAFI` y `CRVIV`, una vez por base
  (parámetro `dcasa_base.diarios_financiamiento_creados`), sin pisar uno que ya exista con ese código o ese nombre.
- **Pruebas**: `dcasa_base/tests/test_reglas_gerencia.py` (cada camino de cobro, anular, borrador, notas, devolución,
  saldo a favor, Tafi y Crediviva y su migración), `dcasa_invoice/tests/test_primer_abono.py` y `test_estado_abono.py`
  (30 días, cambio de mes, migración del parámetro), `dcasa_contabilidad/tests/test_primer_abono_banco.py`,
  `dcasa_brian/tests/test_reglas_gerencia.py` y `website_dcasa/tests/test_pedidos_web_sin_vendedora.py`.

### Campos que Odoo calcula con SQL directo (`models/campos_contables.py`)

Las reglas de registro no frenan un campo que Odoo calcula saltándose las reglas (`bypass_access`); solo lo frena
el grupo del campo, y esos campos traían «Facturación» (que la vendedora tiene para cobrar). Se les pide
contabilidad (`account.group_account_readonly` o `account.group_account_manager`):

- `res.partner.debit`: lo que la tienda le debe a cada proveedor.
- `account.journal.kanban_dashboard` y `kanban_dashboard_graph`: facturas de proveedor por pagar y retrasadas,
  y el saldo del banco y de la caja (las tarjetas del tablero de Facturación).

### Lo que queda abierto a propósito o fuera de este cambio

- **Devoluciones de dinero a un cliente** (pago saliente a un cliente): solo Gerencia y administradores
  (`models/cobros.py`, decisión A7). Las reglas de Facturación y de Caja ya solo dejan ver cobros entrantes.
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

---

## Roles y grupos (mapa completo)

Puesto al día el 2026-10-18 contra `security/*.xml` y `security/ir.model.access.csv` de cada módulo. En la ficha del
usuario, la sección **D'CASA** tiene dos selectores: el rol (Vendedora o Gerencia) y **Nómina** (Administra la nómina).
Los roles se arman con grupos estándar de Odoo; casi no hay permisos nuevos.

| Rol | Grupo (xmlid) | Qué incluye | Qué ve y hace |
|---|---|---|---|
| **Vendedora** | `dcasa_base.group_vendedora` | Ventas «todos los documentos», Facturación (`account.group_account_invoice`), Inventario usuario | Cotiza, confirma y factura lo suyo (no cobra: «el cobro solo en Caja», 2026-10-17), despacha, atiende Conversaciones y Socios. Descuento hasta el tope. No ve nada contable de un jefe, ni costos, ni ganancia, ni Nómina (solo **Mis gastos por reembolsar**), ni Empleados. Su Inicio muestra solo lo suyo. |
| **Caja** | `dcasa_base.group_caja` | Vendedora + Ventas «todos los documentos» (`sales_team.group_sale_salesman_all_leads`) | Ve, factura y **cobra** todas las cotizaciones, pedidos, facturas y cobros de clientes. Sin contabilidad ni costos; descuento con tope. Anular, notas de crédito, devoluciones y un primer abono menor a la mitad: Gerencia. No se le asigna a nadie al instalar: lo da un administrador (ver arriba, «Dar el rol Caja»). |
| **Gerencia** | `dcasa_base.group_gerencia` | Vendedora + gerente de Ventas + contador (`account.group_account_user`) + gerente de Inventario y de Compras + gestor de productos + **Administra la nómina** | Todo lo de la tienda: descuentos sin tope, existencias a mano, fusión de contactos, costos y ganancia, Estadísticas, Comparar ventas, reglas del programa de vendedores. El usuario `admin` nace en Gerencia. No incluye Ajustes técnicos ni gestión de usuarios ni el diseñador del sitio. |
| **Contabilidad** | `account.group_account_user` / `account.group_account_manager` / `account.group_account_readonly` | Grupos de Odoo | Todo lo contable (reglas «todo» en `dcasa_reglas_contables.xml`); el lector solo lee. Ven el menú Empleados. |
| **Administra la nómina** | `dcasa_nomina.group_nomina` | Gerente de RR. HH. + contador | Planillas, sueldos, liquidaciones, reembolsos, bono por meta. Gerencia lo incluye. |
| **Administradores** | `base.group_system` | Ajustes técnicos y usuarios | Lo anterior más: Registro de acciones, Consumo y Ajustes de Brian; Accesos al panel; Cargar datos del sistema anterior; Correo a clientes. Su doble factor es obligatorio con `DCASA_2FA_OBLIGATORIO=1`. |
| **Bodega** | *no hay grupo propio*: `stock.group_stock_user` (usuario) o `stock.group_stock_manager` (gerente) de Odoo | — | Usuario: entregas, recepciones y **Escáner** (buscar). Gerente: además *Códigos de barras* e *Historial de etiquetas*. Contar existencias y cambiar precios en el Escáner: solo Gerencia. |
| **Juan** (usuario técnico) | `dcasa_conversaciones.group_juan` | Ningún otro grupo | Solo ve las herramientas de Juan; sin permisos internos, sin clave de API ni contraseña. |
| **Portal** (cliente con cuenta de la tienda) | `base.group_portal` | — | Su `/my` (lleva a `/mi-cuenta`), sus pedidos y facturas en PDF, cambiar contraseña y direcciones. |
| **Público** (visitante, socio con PIN) | `base.group_public` | — | Sitio, tienda, carrito, `/socios` y `/mi-cuenta` con celular + PIN (una marca en la sesión, no un usuario de Odoo). |

Quién ve cada menú y cada pantalla de los módulos propios: [MODULOS.md](MODULOS.md).

## Interruptores

Lo que se enciende o se apaga sin tocar código (o con un cambio de una línea). Todos vienen como se indica en este commit.

| Interruptor | Dónde | De fábrica | Qué hace |
|---|---|---|---|
| Tope de descuento de la Vendedora | *Ajustes de Ventas › Descuento máximo de la vendedora* (`dcasa.descuento_max_vendedora`) | 10 % | Tope sobre el pedido entero; Gerencia sin tope |
| `DCASA_2FA_OBLIGATORIO` / `DCASA_2FA_ALCANCE` | `edge/wrangler.jsonc` | `1` / `admins` en los dos entornos | Doble factor obligatorio (rescate: `DCASA_2FA_RESCATE`) |
| `DCASA_PUERTA_OBLIGATORIA` | `edge/wrangler.jsonc` | producción `0`, staging `1` | Puerta del equipo `0` → `avisar` → `1`; sin los cuatro secretos queda apagada aunque diga `1` |
| `DCASA_PUERTA_EXIGIR_CORREO` | `edge/wrangler.jsonc` | `0` | El correo de Access debe ser el del usuario de Odoo |
| `TIENDA_ESTATICA` | `edge/wrangler.jsonc` | producción `off`, staging `on` | Caché de páginas anónimas en el borde |
| Turnstile | `TURNSTILE_SITE_KEY` + `TURNSTILE_SECRET` (`DCASA_TURNSTILE=off` lo apaga) | apagado | Captcha invisible en login, formularios y `/socios` |
| `DCASA_ROBOTS_IA` | variable | `equilibrada` | robots.txt para rastreadores de IA |
| Programa de vendedores | `vendedores.programaActivo` en `addons/dcasa_socios/data/puntos.json` | encendido | Comisiones del programa |
| Canje de vendedores externos / en efectivo | `canje.externosHabilitado` / `efectivoHabilitado` en `puntos.json` | **apagados** | Esperan dictamen del abogado y la contadora; Ajustes los muestra de solo lectura y el servidor los ignora |
| Correo a clientes | `RESEND_API_KEY` + *Ventas › Configuración › Correo a clientes* (`dcasa_correo.enviar_a_clientes`, `al_pagar`) | **apagado** | Factura, abono y bienvenida por correo |
| Factura electrónica DGI | `l10n_pa_fe_activo` de la empresa (`dcasa_fe_pa`) | **apagada** y el módulo no se instala | Envío al PAC |
| Constructor visual del sitio | `dcasa_interfaz.sitio_editable` (Ajustes técnicos) | **apagado** | El sitio se edita por código |
| Black Weekend | `DCASA_BLACK_WEEKEND` y su ventana | producción `0`, staging `1` | Campaña visible |
| Juan: canales y bot | *Conversaciones › Configuración › Ajustes de Juan* | WhatsApp QR y Telegram sí; API oficial, Messenger e Instagram no | Qué canales atiende el asistente |
| Tope de gasto de IA de Brian | *Brian › Ajustes* | 0 (sin tope) | Corta las llamadas al modelo al llegar |
| Salidas de emergencia del arranque | `DCASA_PERMITIR_BAJAR`, `DCASA_HUMO=0` (panel del Worker) | sin poner | Solo mientras hagan falta ([OPERACION.md](OPERACION.md)) |

## Reglas no negociables de Socios y Vendedores

Resumen de [`CLAUDE.md`](../CLAUDE.md); el detalle está en [SOCIOS.md](SOCIOS.md) y [VENDEDORES.md](VENDEDORES.md).

**Socios** (reglas de DCasa-Referidos):

1. Ninguna cifra fuera de `addons/dcasa_socios/data/puntos.json`; un `null` o `PENDIENTE` no se rellena a ojo.
2. No hay columna de saldo: el saldo es la suma de `dcasa.movimiento`.
3. El libro no se edita ni se borra (ACL de solo lectura para todos; lo escribe el sistema): se corrige con asientos
   contrarios con motivo.
4. El referido se paga con la primera compra que da puntos; el padrino se escribe una vez.
5. Un cliente y un socio son la misma ficha (`res.partner`), llave = celular.
6. `DCASA_PIN_PEPPER` jamás se rota.

**Vendedores:**

1. Las cifras de fábrica viven solo en la sección `vendedores` de `puntos.json`; Gerencia y administradores las ajustan
   en *Ajustes › Programa de vendedores* como una capa con versión y vigencia hacia adelante (`dcasa.vend.reglas`). El
   código lee siempre `dcasa.vend.reglas._vigentes()`.
2. Libro propio e inmutable (`dcasa.vend.movimiento`); el saldo es la suma.
3. Nada se paga por afiliar ni por reclutar; solo por ventas **pagadas**; un solo nivel; un solo patrocinador.
4. Un tope o un error del programa **nunca** hace fallar una venta (la comisión corre en un savepoint tras el pago).
5. Canje de externos y en efectivo apagados hasta el dictamen; el servidor los ignora aunque alguien los mande.
6. La escalera de comisión solo cambia hacia adelante; lo ya acreditado no se recalcula.

## Superficie RPC (lista blanca)

Odoo deja llamar por `/web/dataset/call_kw` (y `/json/2`) a **todo método público** de un modelo, sin mirar el ACL al
despachar. Un método público que usa `sudo()` sin exigir grupo sería una puerta abierta. Por eso:

- `addons/dcasa_base/tests/test_superficie_rpc.py` recorre todos los modelos y **falla** si un método público definido en
  `addons/` no está en `LISTA_BLANCA` con su motivo (331 entradas en este commit; las que más: `dcasa_conversaciones`
  80, `dcasa_socios` 54, `dcasa_nomina` 28, `dcasa_contabilidad` 26, `dcasa_brian` 25). También falla si una entrada ya
  no es pública, si falta un motivo, o si un botón de vista apunta a un método `@api.model`.
- Los modelos abstractos `brian.herramientas`, `brian.proveedores`, `brian.politica`, `dcasa.mantenimiento`,
  `dcasa.fe.pac`, `dcasa.fe.pac.simulado` y `dcasa.correo` no exponen **nada**.
- Desde internet, el borde además bloquea `/jsonrpc`, `/xmlrpc*`, `/json/2*`, `/web/database/*`, `/doc-bearer*` y
  `/dcasa/juan/*` ([ARQUITECTURA.md §2.8](ARQUITECTURA.md)).
- Regla para todo método nuevo: hacerlo privado (`_nombre` o `@api.private`) o exigir el grupo en el servidor **antes**
  de cualquier `sudo()`, y anotarlo con su motivo.

## Privacidad

- **Datos personales solo en Odoo.** Nombres, correos, celulares, cédulas y facturas de clientes y del equipo nunca van al
  repositorio, a documentos ni a pruebas (hay pruebas que buscan correos reales dentro de los módulos). La carga del
  sistema anterior viaja por la pantalla de Odoo, nunca por Git.
- **PIN de socios:** PBKDF2-SHA256 con sal por socio y la pimienta `DCASA_PIN_PEPPER`, que vive fuera de la base
  (`dcasa_socios/models/res_partner.py`). Un volcado robado sin la pimienta no se puede atacar por fuerza bruta.
  Intentos fallidos bloquean la cuenta; Gerencia reinicia el PIN (queda nota en el historial).
- **Mi cuenta** (`/mi-cuenta`): todo se lee filtrado por la ficha del cliente; un pedido ajeno responde 404. A quien entra
  con PIN no se le enseñan cédula, dirección, otros teléfonos, el correo entero ni PDF; reclamar una ficha con compras
  exige el código de la factura. Detalle: [SOCIOS.md › Mi cuenta](SOCIOS.md#mi-cuenta).
- **Brian y Juan** nunca ven ni cambian contraseñas, claves ni la pimienta; el contenido de adjuntos y mensajes de
  clientes es **dato, no instrucción**. Los registros del puente nunca llevan el QR, credenciales, textos de clientes ni
  números completos.
- **Accesos al panel** se guardan 180 días; las conversaciones de Brian se depuran con su propio plazo.

## Políticas del sitio: dónde viven y cómo se cambian

| Política | Dónde vive | Cómo se cambia |
|---|---|---|
| Privacidad (`/privacidad`) | `addons/website_dcasa/views/legal_templates.xml` (`privacidad_cuerpo`) | En el código y con un despliegue (el sitio no se edita con el constructor) |
| Términos y condiciones (`/terminos`; `/terms` redirige) | Mismo archivo (`terminos_cuerpo`) | Ídem |
| Términos del programa Socios (`/socios/terminos`) | `addons/dcasa_socios/views/socios_templates.xml` (`socios_terminos`) | Ídem; las cifras salen de `puntos.json` |
| Términos de vendedores (`/vendedores/terminos`) | `addons/dcasa_socios/views/vendedores_templates.xml` (`vendedor_terminos`) | Ídem |
| Garantía, cambios y términos impresos en la factura | Texto inicial en `addons/dcasa_invoice/models/res_company.py` (`TEXTOS_INICIALES`), se escribe una vez | *Ajustes › Empresas › Documentos D'CASA* (no se vuelve a pisar) |
| Condiciones de abono (hoja de dos copias) | Texto inicial en `addons/dcasa_abonos/models/condiciones.py` (`CONDICIONES_INICIALES`) | *Ajustes › Empresas › Documentos D'CASA* |
| Plazo de los apartados por la web | Parámetro `website_dcasa.apartado_dias` | *Sitio web › Configuración › Ajustes* |
| Lo que Juan dice de garantía y compra | Fichas de conocimiento (`dcasa_conversaciones/data/conocimiento_data.xml`), **inactivas** de fábrica | *Conversaciones › Conocimiento del bot*, con la revisión de la dueña |

Regla para todas: no prometen plazos, garantías ni condiciones que el dueño no haya fijado; se revisan con un abogado.
La ficha de producto de Odoo trae promesas propias («devolución de 30 días») que `website_dcasa` apaga en cada
despliegue.
