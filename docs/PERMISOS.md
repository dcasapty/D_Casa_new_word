# Qué ve cada rol (permisos de la tienda)

Para la dueña: **quien vende no ve nómina ni la contabilidad de un jefe**, ni por el menú ni por un enlace.
Para quien programa: cómo está armado y cómo se comprueba. Reglas en
`addons/dcasa_base/security/dcasa_reglas_contables.xml`; pruebas en
`addons/dcasa_base/tests/test_permisos_contables.py` y `test_permisos_vendedora.py` (menús).

Más abajo: [roles y grupos](#roles-y-grupos-mapa-completo) · [interruptores](#interruptores) ·
[reglas de Socios y Vendedores](#reglas-no-negociables-de-socios-y-vendedores) ·
[superficie RPC](#superficie-rpc-lista-blanca) · [privacidad](#privacidad) ·
[políticas del sitio](#políticas-del-sitio-dónde-viven-y-cómo-se-cambian).

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

---

## Roles y grupos (mapa completo)

Puesto al día el 2026-10-18 contra `security/*.xml` y `security/ir.model.access.csv` de cada módulo. En la ficha del
usuario, la sección **D'CASA** tiene dos selectores: el rol (Vendedora o Gerencia) y **Nómina** (Administra la nómina).
Los roles se arman con grupos estándar de Odoo; casi no hay permisos nuevos.

| Rol | Grupo (xmlid) | Qué incluye | Qué ve y hace |
|---|---|---|---|
| **Vendedora** | `dcasa_base.group_vendedora` | Ventas «todos los documentos», Facturación (`account.group_account_invoice`), Inventario usuario | Cotiza, factura y cobra a clientes, despacha, atiende Conversaciones y Socios. Descuento hasta el tope. No ve nada contable de un jefe, ni costos, ni ganancia, ni Nómina (solo **Mis gastos por reembolsar**), ni Empleados. Su Inicio muestra solo lo suyo. |
| **Caja** | *no hay grupo propio en este commit* | Para Brian, el rol «cajero» = Facturación + Ventas todos + Inventario usuario (`dcasa_brian/models/herramientas_usuarios.py`) | En la práctica cobra lo mismo que la Vendedora (que ya tiene Facturación). Según la bitácora hay trabajo en curso (rama `permisos-vendedoras`) con un rol Caja y un interruptor; **no está en este commit**. |
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
