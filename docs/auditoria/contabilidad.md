# Auditoría `contabilidad`: corrección financiera y fiscal (Panamá)

Alcance: `addons/dcasa_contabilidad`, `dcasa_invoice`, `dcasa_socios`, `dcasa_base`. Fecha: 30/09/2026.
Auditoría **estática** (no se ejecutó ningún test). `vendor/odoo` sí está presente: lo verifiqué ahí donde se indica
`vendor/…`; lo que no pude comprobar va marcado **(por verificar)**. Numeración de hallazgos `C-xx`.

## 1. Resumen ejecutivo

1. **La base contable es sólida.** Los reportes salen solo de apuntes publicados, con sumas agrupadas en SQL y
   redondeo con `currency.round`; el balance de comprobación y el balance general tienen chequeo de cuadre propio; la
   conciliación trabaja con `currency.round/is_zero` (nunca compara floats con `==`) y es reversible; el libro de
   puntos es inmutable y el programa usa centavos enteros. No encontré un error de signo ni de fórmula en
   estado de resultados, balance, comprobación ni ITBMS.
2. **El test de la factura INV/2026/00821 es correcto en cifras** ($171,97 + $158,02 = $329,99; ITBMS por línea
   12,04 + 11,06 = 23,10; global 329,99 × 7 % = 23,0993 → 23,10; total $353,09), pero **no discrimina**: pasa igual con
   redondeo por línea o global, y solo pasa porque el test busca a propósito el impuesto «se suma al precio». Con el
   impuesto por defecto de la empresa («ITBMS 7% incluido», `dcasa_base/__init__.py:65-76`) esas mismas líneas dan
   **total $329,99**. Es la misma pregunta abierta de `enterprise-gap` E-01 (CRÍTICO por confirmar): ver C-01.
3. **Lo más serio antes de producción**: (a) la factura electrónica DGI no existe (obligación legal, C-02); (b) no hay
   fechas de bloqueo ni cierre de periodo configurados (C-03); (c) los puntos no se revierten si el pago se cancela o
   se desconcilia, y hay cuatro huecos más en la integración factura ↔ puntos (C-10 a C-14); (d) el libro mayor
   muestra totales equivocados cuando se trunca (C-06); (e) la API de reportes se puede llamar sin pasar por el
   control de permisos (C-07, por verificar); (f) la importación de extracto puede perder movimientos legítimos
   idénticos (C-08).
4. **Funciones de Enterprise que aún faltan**: antigüedad de saldos (cobrar/pagar), libro de terceros, flujo de
   efectivo, comparativos por periodo, activos fijos/depreciación, ingresos diferidos, seguimiento de cobros,
   reglas de conciliación, retenciones, factura electrónica, nómina. Detalle en §5.

## 2. Verificación del test de la factura INV/2026/00821

`addons/dcasa_invoice/tests/test_dcasa_invoice.py:352-378`. Cálculo manual:

| Línea | Base | ITBMS 7 % exacto | Redondeado |
|---|---|---|---|
| Colchón | 171,97 | 12,0379 | 12,04 |
| Cama | 158,02 | 11,0614 | 11,06 |
| Suma por línea | **329,99** | | **23,10** |
| Global | 329,99 | 23,0993 | 23,10 |

Total 329,99 + 23,10 = **353,09** ✓. Las aserciones son correctas. Debilidades:
- No fija el método de redondeo (`tax_calculation_rounding_method`, por línea por defecto) ni un caso donde por línea y
  global difieran (p. ej. 3 líneas de $0,50 → 0,035 c/u: por línea 0,12, global 0,105 → 0,11). Para el SFEP el ITBMS
  va por ítem, así que conviene fijarlo y probarlo.
- Usa `search(... price_include=False, amount=7, limit=1)`: si el impuesto no existe la prueba falla con un mensaje
  críptico (`amount_tax` 0), y oculta que el impuesto por defecto es otro (C-01).
- `SociosCommon` (`dcasa_socios/tests/common.py:15-19`) repite el mismo patrón: todos los tests de puntos usan el
  impuesto «se suma», nunca el que la tienda usa de verdad.

## 3. Hallazgos

Severidad: CRÍTICO · ALTO · MEDIO · BAJO. «(pv)» = por verificar contra el código de Odoo 19.

### Fiscal y configuración

#### C-01 · CRÍTICO (por confirmar) · El impuesto por defecto suma 0 % sobre precios «+ITBMS»
- Evidencia: `dcasa_base/__init__.py:65-76` fija `company.account_sale_tax_id` = «ITBMS 7% incluido» y
  `account_price_include = 'tax_included'` (`:76`); el Excel trae precios «+ITBMS» y la factura real 00821 los suma.
- Escenario: producto a $329,99 con el impuesto por defecto → la factura total es $329,99 y el ITBMS $21,59 (extraído),
  no $353,09 / $23,10. El reporte de ITBMS (`reportes.py:253`) y el total por cobrar heredan el error.
- Arreglo: lo decide la dueña con una factura real (coordinado con `enterprise-gap` E-01). Si son «+ITBMS»: impuesto
  por defecto «se suma», y añadir un test con el impuesto **por defecto** de la empresa que reproduzca $353,09.

#### C-02 · ALTO (documentado, bloqueante legal) · Sin factura electrónica DGI
- Evidencia: solo la pantalla «En desarrollo» (`dcasa_contabilidad/static/src/js/en_desarrollo.js`, `views/menus.xml:55`);
  la plantilla `dcasa_invoice/views/report_invoice.xml` no imprime CUFE, QR ni número de autorización.
- Efecto: no es un documento fiscal válido si la DGI exige SFEP a D'CASA (la obligación y el calendario los confirma el
  contador; no los asumo). Además, cuando exista CUFE una factura no debe poder volver a borrador
  (`account.move.button_draft` está abierto a Facturación).
- Arreglo: elegir PAC; módulo `dcasa_fe` con CUFE/QR en la plantilla, bloqueo de `button_draft`/`button_cancel` con CUFE,
  y notas de crédito electrónicas. Hasta entonces, definir con el contador qué documento se entrega al cliente.

#### C-03 · MEDIO · Nada configura fechas de bloqueo ni cierre de periodo
- Evidencia: `grep` de `fiscalyear_lock|tax_lock|hard_lock|sale_lock|purchase_lock` en `addons/`: cero resultados.
  `reportes.py` calcula siempre «en vivo» de los apuntes, así que cualquier asiento retroactivo cambia un periodo ya
  declarado.
- Escenario: ITBMS de agosto declarado con $1.250,00 por pagar; en septiembre alguien postea una factura con fecha
  10/08 → el reporte de agosto ahora dice $1.260,50 y ya no coincide con la declaración.
- Arreglo: las fechas de bloqueo son Community. Fijar en `dcasa_base` (o en el procedimiento de cierre) «bloqueo de
  impuestos» al presentar la declaración y «bloqueo fiscal» al cerrar el mes/ejercicio; probar que un posteo
  anterior falla. Además ver C-09 (la conciliación reescribe asientos publicados).

#### C-04 · MEDIO · RUC y DV sin validación
- Evidencia: `dcasa_base/models/res_partner.py:202-206` solo exige que el DV sea dígito (`size=2`); `vat` no se valida
  (`test_dcasa_base.py:394` solo prueba «X»). `dcasa_invoice/models/formato.py:86` reconoce formato de cédula solo para
  el rótulo «Cédula/RUC».
- Escenario: cliente con RUC `155779346-2-2026` y DV `77` o vacío: la factura sale con «DV77» o sin DV y nadie avisa; un
  RUC mal tecleado llega al PAC/DGI y la factura se rechaza.
- Arreglo: constraint que, para personas jurídicas, exija DV y lo valide con el algoritmo módulo 11 de la DGI (validar
  la fórmula con el contador/DGI, no inventarla), y formato de RUC/cédula. Test con RUC real y uno erróneo.

#### C-05 · MEDIO · Retenciones y exentos sin soporte; `type_tax_use='none'` cuenta como compra
- Evidencia: `grep retenci|withhold` en `addons/`: cero. `reportes.py:265-266`: todo lo que no es `sale` se trata como
  compra (signo +1).
- Efecto: no hay ITBMS retenido (agentes de retención) ni ISR retenido; un impuesto `none` (p. ej. una retención
  configurada así) inflaría el «crédito fiscal». Los exentos/0 % sí salen con base (bien, `test_itbms_incluye_ventas_exentas`).
- Arreglo: definir con el contador si D'CASA retiene o le retienen; si aplica, impuestos de retención con cuenta propia
  y filas separadas en `itbms()`; excluir `none` del crédito fiscal.

#### C-06b · BAJO · Etiqueta «con/sin ITBMS» engañosa en facturas mixtas
- `dcasa_invoice/models/account_move.py:193-204`: `all(price_include)`; con una línea incluida y otra no, el encabezado
  dice «sin ITBMS» y la línea incluida muestra `price_subtotal` (neto) con un precio unitario que sí trae ITBMS →
  cantidad × precio ≠ importe (p. ej. 1 × $107,00 incluido imprime importe $100,00). Arreglo: marcar por línea o
  unificar la base de la columna.

### Reportes

#### C-06 · MEDIO · Libro mayor: totales equivocados cuando se trunca a 2.000 líneas
- Evidencia: `reportes.py:162-176`: `debe/haber` se suman de `detalle` (solo las primeras 2.000 líneas) y
  `final = inicial + debe − haber`. La consulta agrupada ya calculó los totales reales (`_sumas_por_cuenta`).
- Escenario: CxC con 2.500 líneas en el periodo: `final` no iguala el saldo del balance; el Excel (`controllers/main.py:292`)
  exporta «Total de la cuenta» truncado sin aviso.
- Arreglo: totales y `final` desde la suma agrupada; `detalle` solo para mostrar; avisar el truncado también en Excel/PDF.
  Además es N+1 consultas (una por cuenta): una sola consulta agrupando por cuenta.

#### C-07 · MEDIO (confirmado en vendor) · Los reportes se pueden pedir sin pasar por el control de permisos
- Evidencia: `reportes.py:313-317`: solo `obtener()` exige `account.group_account_readonly`; `balance_general()`,
  `estado_resultados()`, `libro_mayor()`, etc. son públicos (sin `_`) en un `AbstractModel` y se pueden invocar por RPC.
  Lo único que los frena es el ACL de `account.move.line`, y `vendor/odoo/addons/sale/security/ir.model.access.csv:9`
  da **lectura de apuntes a `group_sale_salesman`**: una vendedora llamando por RPC a `balance_general` ve el balance completo. `dcasa.conciliacion` (`conciliacion.py:123-200`) tampoco verifica grupo: el menú sí
  (`account.group_account_user`), la API no (el ACL de escritura de `account.bank.statement.line` es `group_account_basic`,
  `vendor/…/account/security/ir.model.access.csv:33`, algo más ancho que el menú).
- Arreglo: renombrar los motores a `_balance_general`… o repetir el `has_group` en un helper común; en conciliación,
  exigir `group_account_user` en `conciliar/automatico/deshacer`. Test: usuario de ventas que llama directo a `balance_general`.

#### C-06c · BAJO · Multiempresa: `_inicio_ejercicio` usa `env.company` y el dominio `env.companies`
- `reportes.py:64` vs `:71`. Con una sola empresa (hoy) no importa; con varias y años fiscales distintos, el
  «resultado del ejercicio» se parte mal. También `_moneda()/_r()` toman la moneda de la empresa activa. Aceptable
  mientras D'CASA sea una empresa (docs/CONTABILIDAD.md lo dice); dejarlo anotado.

#### C-06d · BAJO · Presupuesto: sin bloqueo en servidor y % en cero
- `presupuesto.py:135-139, 153-160`: aprobar/cerrar no impide editar líneas (solo `readonly` en la vista,
  `presupuesto_views.xml:56`); `porcentaje` es 0 si lo planeado es 0 aunque haya gasto real (`:118`); `_compute_real`
  hace una búsqueda por línea y suma en Python (lento con miles de apuntes). Sin validación de fechas solapadas ni de
  cuenta de otra empresa. Arreglo: `write` que rechace cambios de líneas fuera de borrador; usar `_read_group`.

### Conciliación bancaria e importación

#### C-08 · MEDIO · Importar extracto descarta movimientos legítimos idénticos
- Evidencia: `wizard/importar_extracto.py:90-91`: la clave `(fecha, concepto, monto)` se compara con un **conjunto**.
- Escenario: dos depósitos Yappy «YAPPY JUAN 5.00» el mismo día (legítimos). Extracto cortado a medianoche: el primer
  archivo trae uno; el segundo trae ambos → los dos quedan «ya importados» y se pierden $5,00 sin aviso. Además la
  referencia del banco (`f['referencia']`) no entra en la clave ni se usa `unique_import_id`.
- Arreglo: comparar con contadores (`Counter`), o mejor usar la referencia del banco como `unique_import_id` y avisar
  cuántos se omitieron. Test con dos filas idénticas en archivos solapados.

#### C-09 · MEDIO · `dcasa_conciliar` reescribe el asiento publicado sin bloqueo de fila ni validación de entradas
- Evidencia: `conciliacion.py:109-111` (`force_delete`, `skip_readonly_check`), `:84` y `:96`.
  (1) Sin `SELECT … FOR UPDATE` de la línea del extracto: dos usuarios que concilian el mismo movimiento a la vez leen
  el mismo pendiente; uno borra la línea transitoria y el otro falla o duplica (Odoo reintenta por serialización, pero no
  es garantía). Patrón correcto ya usado en `dcasa_socios/models/dcasa_canje.py:97`.
  (2) `apunte_ids` y `cuenta_id` vienen del cliente y no se validan: apunte ya conciliado (`amount_residual` 0 →
  línea de $0), de otra empresa, de signo contrario, o `cuenta_id` = cuenta del propio banco/de cobrar.
  (3) `force_delete`/`skip_readonly_check` son los mismos que usa Odoo en su propia conciliación
  (`vendor/…/account/models/account_bank_statement_line.py:471`) y las fechas de bloqueo se siguen comprobando al escribir
  los apuntes (`account_move_line.py:1854`): **no es un hueco**; solo falta una prueba con fecha bloqueada.
- Arreglo: bloquear la fila al inicio; validar que cada apunte esté publicado, sin conciliar, conciliable, de la misma
  empresa y del signo de `pendiente`, y que `cuenta_id` no sea liquidez.

#### C-09b · BAJO · Conciliación automática sin savepoint y solo en moneda de la empresa
- `conciliacion.py:120-130` y `importar_extracto.py:103`: un error en una línea aborta todo el import (incluidas las
  líneas ya creadas). Usar `with self.env.cr.savepoint()` por línea. `saldo = -apunte.amount_residual` (`:86`) es en
  moneda de la empresa pero el apunte puede ser en otra moneda (p. ej. factura de proveedor en EUR): queda un residual en
  moneda extranjera. El docstring lo asume USD; añadir un `UserError` si `apunte.currency_id != moneda`.

#### C-09c · BAJO · Lectura de CSV: menos signo final, fechas ambiguas
- `conciliacion.py:245` `texto.strip('()-+')` quita un `-` final pero `negativo` solo mira el inicial: «45.00-» (formato
  de algunos bancos) se importa **positivo** (un retiro se vuelve depósito). Fechas: `%d/%m/%Y` primero y `%m/%d/%Y` de
  respaldo (`:189`): un banco con m/d/a se lee mal de forma silenciosa los días ≤ 12. Arreglo: soportar signo final y
  «CR/DB», y exigir un único formato de fecha por archivo (detectado en la primera fila no ambigua).
  La compleja heurística de columnas (`startswith`) puede confundir «Número de cuenta» con Referencia (`importar_extracto.py:23,45`).

### Cheques

#### C-15 · BAJO · Monto en letras del cheque siempre en «Dólares»
- Evidencia: `cheque.py:21`: `MONEDAS.get(name, ('Dólar', 'Dólares'))`. La factura sí cae a `amount_total_words` para
  otras monedas (`account_move.py:188-190`).
- Escenario: pago a un proveedor en EUR por 500,00 → «Quinientos Dólares con 00/100». Arreglo: si la moneda no está en
  `MONEDAS`, dejar el texto de `super()`.
- Numeración, anulación y post-fechados: la numeración y la anulación son las de `account_check_printing` (Community);
  D'CASA no añade nada. **No existe el concepto de cheque post-fechado** (un pago con fecha futura se contabiliza en su
  fecha; no hay cuenta de «cheques por cobrar/pagar» ni recordatorio). Es una brecha, no un error.

### Facturas y formato

La factura (`dcasa_invoice`) está bien: `monto_en_letras` usa `round(round(x,2)*100)` a enteros, apócope correcta
(«veintiún mil», «un millón de dólares», «ciento un dólares» comprobados a mano para 21.000, 1.000.000, 101 y
100.000). Pendiente: los tests unitarios de `test_formato.py` cubren `numero_en_letras` pero **no `monto_en_letras`**
(solo lo cubre indirectamente el cheque, `test_contabilidad.py:304`): añadir casos de 0,05 / 1,00 / 21.000,99 /
1.000.000,00 / 1.000.001,00 y negativos. «Pagada» se imprime con `payment_state in ('paid','in_payment')`
(`account_move.py:144`): un pago registrado pero aún no conciliado con el banco ya dice «Pagada el…». Es el
comportamiento de Odoo y está documentado en el docstring; mantenerlo, pero el contador debe saberlo.

### Programa de socios (`dcasa_socios`)

#### C-10 · MEDIO · Los puntos no se revierten si el pago se cancela o se desconcilia
- Evidencia: `account_move.py:15-20` solo actúa al *entrar* en `paid/in_payment`: Odoo llama `_invoice_paid_hook` únicamente
  desde `_reconcile_post_hook` (`vendor/…/account/models/account_move_line.py:2785-2794`) y al postear una factura de total 0;
  desconciliar o cancelar el pago no dispara nada. Solo
  `button_draft`/`button_cancel` (`:31-39`) y notas de crédito (`:41-56`) anulan la compra.
- Escenario: factura $107 pagada con cheque → 107 puntos (+ referido: 500 al padrino y 250 al cliente). El cheque
  rebota y el pago se cancela; la factura vuelve a «no pagada» pero los 857 puntos siguen. Al volver a pagar no suma
  de nuevo (`UNIQUE(factura_normal)`), así que el daño es el primero: puntos sin cobro.
- Arreglo: al perder el estado pagado (desconciliar/`account.partial.reconcile.unlink`/cancelar pago), `_anular` la
  compra si la factura ya no está `paid/in_payment`. Considerar dar puntos solo con `paid` (conciliado con el banco) y no con `in_payment`.

#### C-11 · MEDIO · Factura devuelta a borrador y vuelta a pagar: el cliente nunca recibe sus puntos
- Evidencia: `dcasa_compra.py:120` (`search_count` incluye compras anuladas) + `UNIQUE(factura_normal)` (`:163`, «también si se anuló»).
- Escenario: vendedora corrige una línea: `button_draft` (anula la compra, libera el sello del referido), repostea, el
  cliente paga → `_registrar_desde_factura` ve la compra anulada y devuelve vacío: **cero puntos para siempre** y, si era
  su primera compra, el referido tampoco se paga. La regla «una factura, una carga» está pensada contra fraude, pero
  aquí castiga un flujo normal de Odoo.
- Arreglo: permitir re-registrar si la compra previa está `anulada` **por borrador/cancelación de la propia factura**
  (reactivar la compra o crear otra con `factura_normal` distinto, p. ej. con sufijo), manteniendo una sola activa.

#### C-12 · MEDIO · Una nota de crédito parcial reposteada descuenta dos veces, y la parcial no cuenta acumulado
- Evidencia: `account_move.py:41-56` y `dcasa_compra.py:220-227`; `button_draft` solo se intercepta para `out_invoice` (`:31`).
  (a) NC parcial de $53,50 sobre una compra de 214 puntos → −53. Si la NC vuelve a borrador y se repostea, el hook corre
  otra vez: −53 de nuevo (−106 en total). Una NC cancelada tampoco devuelve nada.
  (b) `devuelto >= monto` compara **cada NC por separado** con el monto original: dos NC de $60 y $40 sobre $100 nunca
  anulan la compra; los puntos netos quedan en 0 pero la compra sigue «activa» y el referido cobrado se queda. Con una
  compra de $25 y una NC de $24 (queda $1, por debajo del mínimo de $20) también.
- Arreglo: guardar qué NC ya descontó (`nota_credito_id` en el movimiento, índice único) para que sea idempotente y
  reversible; calcular lo devuelto como suma de todas las NC posteadas de la factura y anular (con referido) cuando el
  neto cae bajo el mínimo o a cero. Redondeo: `-(puntos*devuelto // monto)` quita de menos (floor hacia cero); aceptable
  pero acumulable, calcularlo sobre el total devuelto y restar lo ya descontado.

#### C-13 · MEDIO · Un premio de descuento mayor que la venta deja un total negativo; cancelar la venta no devuelve el premio
- Evidencia: `wizard/dcasa_cobrar_premio_wizard.py:49` (`price_unit = -canje.valor`, sin tope) y
  `sale_order.py:32-42` (solo marca `entregado` al confirmar; no hay `action_cancel` en el módulo).
- Escenario (a): pedido de $3,00 con premio de $5,00 → total −$2,00; el canje queda consumido y la factura es negativa
  (`_registrar_desde_factura` la ignora, `dcasa_compra.py:123`, pero contablemente es un abono a favor que no se paga).
  Escenario (b): la venta confirmada se cancela o su factura se reversa → el canje sigue `entregado` y los puntos no
  vuelven.
- Arreglo: limitar el descuento a lo que queda del pedido o exigir total ≥ 0 al confirmar; al cancelar la orden (o
  reversar la factura) devolver el canje a `solicitado` (si no venció) o reponer los puntos con un reverso.
  Test de ambos.

#### C-14 · BAJO-MEDIO · Condiciones de carrera en topes de referidos
- Evidencia: `dcasa_compra.py:159-178`. El sello `dcasa_referido_pagado_en` del comprador sí se escribe, y Odoo trabaja
  en `REPEATABLE READ` y reintenta por serialización, de modo que dos pagos simultáneos del *mismo* comprador no pagan
  dos veces (bien). Pero el **padrino** no se bloquea: dos ahijados distintos que pagan a la vez leen `cobrados` = 49
  (o `del_mes` = 4.500) y ambos pasan → 51 ahijados / 5.500 puntos al mes, por encima de los topes 50 / 5.000.
  La reserva de canjes sí está bien (`dcasa_canje.py:97`, `FOR UPDATE` sobre el socio).
- Arreglo: `SELECT id FROM res_partner WHERE id = %s FOR UPDATE` sobre el padrino antes de contar (mismo patrón que
  `_pedir`). Costo máximo por carrera: un referido de $7,50; por eso BAJO-MEDIO.

#### C-16 · MEDIO (pv con el negocio) · Clientes genéricos («Consumidor final») acumulan puntos en una sola ficha
- Evidencia: `_registrar_desde_factura` (`dcasa_compra.py:118-128`) acredita a `commercial_partner_id` de cualquier
  factura pagada; solo `sale_order.py:40` excluye al partner público, y solo para el padrino.
- Escenario: si la tienda factura ventas de mostrador a un contacto genérico, todas suman a un solo socio
  («Cliente contado» con 40.000 puntos) y `_dcasa_asegurar_ficha` le crea código de socio. También se abre ficha (con código
  impreso en la factura) a **todo** cliente facturado, sin consentimiento previo (Ley 81/2019; el resto del módulo
  cuida que «una vendedora no la mete al programa»).
- Arreglo: bandera `dcasa_fuera_del_programa` (o exigir celular válido) y excluir genéricos/públicos; decidir
  si la ficha se crea al facturar o solo al reclamarla.

#### C-17 · BAJO · Permisos de gerencia solo en la vista
- `dcasa_canje.py:159-175` (`action_entregar`, `action_cancelar`) y `res_partner.py:377-383` (`action_dcasa_suspender/activar`):
  la vista restringe a `sale_manager`, el método no. `_entregar/_cerrar` usan `sudo()` (`dcasa_canje.py:143,165`), de
  modo que cualquier usuario interno con lectura de canjes puede cancelar uno ajeno por RPC (devuelve puntos) o marcarlo
  entregado; suspender/activar escribe con el ACL normal de contactos (las vendedoras lo tienen). Arreglo: `if not
  self.env.user.has_group('sales_team.group_sale_manager'): raise AccessError` en esos métodos.
  (`action_dcasa_reiniciar_pin` por la vendedora es decisión documentada, no fallo.)

#### C-18 · BAJO · Latentes y decisiones que conviene cerrar
- `reglas.py:488`: `int((base * puntosPorDolar) // 100)` usa float si `puntosPorDolar` deja de ser entero (1,1 ó 0,58):
  el piso de un producto exacto puede caer 1 punto por error de coma flotante. Hoy vale `1`; usar `Fraction`/`Decimal` si cambia.
- `puntosMaximosPorCompra: 50000` sigue «PENDIENTE DE CONFIRMAR» y recorta en silencio (`puntos.json`); `baseDeCalculo`
  'subtotal' usa `itbmsPorcentaje` fijo (7) y falla con ventas mixtas exentas/gravadas. Hoy es `total`.
- El saldo puede quedar negativo tras una anulación posterior al canje (comprar $600, canjear $5, devolver todo: −500). No
  es fuga (`_pedir` exige saldo ≥ puntos) pero hay que decidir si se cobra en la próxima compra; el ajuste manual sí lo
  impide (`dcasa_ajuste_wizard.py:112`).
- Transición: la compra manual usa otro número que la factura de Odoo (`F-000821` → `F821`; `INV/2026/00821` →
  `INV202600821`): si la misma venta se carga a mano y luego existe en Odoo se cuenta dos veces. Y al revés: si el
  `INV/2026/00821` real ya se cargó, una factura nueva con ese número en la base nueva **no dará puntos** (C-11). Fijar
  el siguiente número de la secuencia del diario por encima de la última factura anterior.
- Contabilidad de los puntos: el pasivo («Pasivo del programa», `dcasa_movimiento_views.xml:47`) es un pivote en
  puntos, no en dólares, y no hay asiento ni provisión (100 puntos = $1). El costo de un premio de producto tampoco
  genera asiento. Con la economía actual (~1 % de lo pagado) es inmaterial, pero el contador debe decidir si se
  reconoce (NIIF 15, ingreso diferido) o se documenta como política.

### Configuración y pruebas

#### C-19 · (descartado) `price_include_override`
- Sospeché que el valor por defecto de `price_include_override` fuese la cadena `'default'`, lo que haría inútil el filtro
  de `dcasa_base/__init__.py:63`. **Refutado**: en `vendor/…/account/models/account_tax.py:142-147` el campo solo tiene
  `tax_included`/`tax_excluded` y vacío por defecto; el filtro funciona y `test_compras_siguen_sin_itbms_incluido` lo guarda.

#### C-20 · BAJO · Tarjeta y Yappy como diarios `bank` sin liquidación
- `dcasa_base/__init__.py:8-12`: los cobros con tarjeta se liquidan días después y con comisión; no hay cuenta de
  «tarjetas por cobrar» ni conciliación de lote (la comisión se registra a mano como gasto, `conciliacion.py`). Sirve, pero el
  flujo correcto es: cobro → cuenta por cobrar de procesadora → liquidación neta con comisión.

## 4. Lo que está bien hecho

- **Reportes**: una consulta agrupada por cuenta (`reportes.py:76-80`), solo `parent_state` publicado salvo
  `borradores=True`, exclusión de `off_balance`, saldo inicial correcto para cuentas de resultados (solo el ejercicio
  en curso) y traspaso de ejercicios anteriores a patrimonio (`:100-112`, `:216-246`); todos los tipos de cuenta de
  Odoo quedan cubiertos por alguna sección, así que el balance cuadra sin «cuenta de ajuste». Signos coherentes
  (ingresos = −balance, costos y gastos = +balance; utilidad neta del ER = «Resultado del ejercicio» del balance).
  Base imponible incluso de impuestos 0 %/exentos.
- **Conciliación**: `round`/`is_zero` de la moneda en cada paso, conciliación parcial conservando lo ya conciliado,
  resto a transitoria en vez de inventar cuentas, «deshacer» con la API de Odoo, y el automático exige un único
  candidato con puntaje ≥ 7 (monto + cliente o monto + referencia) — no concilia a la ligera.
- **Libro de puntos**: inmutable por `write/unlink` bloqueados, `UNIQUE(reversa_id)`, `CHECK(puntos <> 0)`, saldo = suma,
  reversos con motivo; centavos enteros (`a_centavos`), redondeo siempre hacia abajo, `FaltaConfigurar` en vez de cero
  silencioso, `UNIQUE(factura_normal)`; `_pedir` bloquea la fila del socio; la anulación deshace el referido y suelta el sello.
  79 tests, incluidos los de topes, caducidad (con la hora de Panamá) y cumpleaños.
- **Facturas**: lo impreso refleja la base (pagos verídicos, sin sello de goma, DV del RUC, monto en letras correcto,
  idioma fijo), funciones puras probadas.
- **Base**: empresa, RUC+DV reales (`155779346-2-2026 DV7`), moneda USD, `es_419` con punto decimal, idempotencia de
  la configuración (`test_se_puede_repetir`) y migraciones para bases existentes.

## 5. Funciones de Enterprise que aún faltan (contabilidad) — coordinado con `enterprise-gap`

| Función Enterprise | Estado en D'CASA | Prioridad |
|---|---|---|
| Antigüedad de saldos cobrar/pagar (0-30-60-90) y libro de terceros | No existe (solo el mayor con `tercero`) | P1 |
| Flujo de efectivo (directo/indirecto) | No existe | P2 |
| Comparativos (periodo anterior, año anterior, columnas por mes) y filtros por diario/analítica/tercero | Un solo periodo | P2 |
| Seguimiento de cobros (`account_followup`) | No; Brian lista «clientes que deben» | P1 |
| Activos fijos y depreciación; ingresos/gastos diferidos | No | P2 |
| Reglas de conciliación guardadas, conciliación por lote, OFX/QIF/CAMT | Solo CSV y reglas fijas | P3 |
| Cierre de ejercicio asistido, fechas de bloqueo configuradas | No configurado (C-03) | P1 |
| Factura electrónica DGI (PAC, CUFE, QR) | No (C-02) | P0 legal |
| Retenciones (ITBMS/ISR), declaración de ITBMS por formulario | Solo resumen base/cuota (C-05) | P1 (validar con contador) |
| Cheque post-fechado, depósito por lote, pago por lote | No | P3 |
| Revaluación de moneda extranjera, multiempresa/consolidación | No aplica hoy (USD, una empresa) | P3 |
| Nómina, gastos | En desarrollo | P1/P3 |

## 6. Casos de prueba que faltan

1. Factura 00821 con el **impuesto por defecto** de la empresa (C-01) y con redondeo por línea vs global.
2. RUC/DV válido e inválido (C-04).
3. Libro mayor con más de `limite` líneas: `final` = saldo del balance (C-06).
4. Usuario de ventas llamando directo a `balance_general` y a `dcasa.conciliacion.conciliar` (C-07, C-09).
5. Importar dos filas idénticas en archivos solapados; «45.00-»; fecha m/d/a (C-08, C-09c).
6. Conciliar con `apunte_ids` ya conciliado/de signo contrario/`cuenta_id` liquidez; dos conciliaciones concurrentes (C-09).
7. Conciliar con fecha en periodo bloqueado (C-03/C-09).
8. Cancelar el pago / desconciliar una factura pagada (C-10); `button_draft` + repago (C-11).
9. NC parcial reposteada, dos NC que suman el total, NC en borrador/cancelada (C-12).
10. Premio mayor que la venta; cancelar la venta con canje entregado (C-13).
11. Dos ahijados pagando a la vez en el tope (C-14; con dos cursores o `FOR UPDATE` verificado).
12. `monto_en_letras` (0,05; 21.000,99; 1.000.000; 1.000.001) y cheque en EUR (C-15).
13. Cuadre cruzado: ITBMS por pagar del reporte = saldo de las cuentas de impuesto del balance en el mismo periodo.

## 7. Plan de arreglo (orden sugerido)

1. Antes de producción: C-01 (pregunta a la dueña), C-03 (fechas de bloqueo), C-02 (elegir PAC y definir el documento
   mientras tanto), C-04, C-16.
2. Corrección de dinero/datos: C-06, C-07, C-08, C-09, C-10, C-11, C-12, C-13.
3. Endurecimiento: C-14, C-17, C-15, C-09b/c, C-06b/c/d, C-20.
4. Brecha Enterprise (§5): antigüedad de saldos y seguimiento de cobros primero.
