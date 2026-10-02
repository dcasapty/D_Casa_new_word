# Contabilidad de D'CASA (`dcasa_contabilidad`)

Construida sobre la contabilidad de Odoo 19 Community (partida doble, plan contable
de Panamá `l10n_pa`, ITBMS). Todo sale de los asientos publicados: no hay cifras
guardadas aparte.

## Qué hay (menú Facturación)

| Menú | Qué hace |
|---|---|
| **Bancos › Conciliación bancaria** | Movimientos del banco sin explicar a la izquierda; a la derecha, las facturas y pagos que los explican (sugeridos por monto, cliente y referencia) o una cuenta para comisiones y cargos. Conciliación parcial, automática (solo lo inequívoco) y «deshacer». Arriba, las **reglas que aplican** al movimiento, con un clic. Una pestaña por banco: Banco, Tarjeta, Yappy, Efectivo. |
| **Bancos › Importar extracto** | **CSV** de la banca en línea (Banco General, BAC, Banistmo, Caja de Ahorros, Yappy…), **OFX/QFX** o **CAMT.053**. En CSV reconoce Fecha, Descripción, Monto o Débito/Crédito, Referencia aunque haya filas de título arriba; separador y codificación se detectan; montos `1,234.56`, `1.234,56`, `(45.00)` o `45.00-`. **Vista previa** antes de importar. No duplica lo ya importado (por el identificador del banco en OFX/CAMT), avisa si el saldo final del banco no coincide y concilia solo lo seguro. |
| **Bancos › Reglas de conciliación** | Las reglas de Odoo (`account.reconcile.model`) con motor propio: si la descripción contiene / no contiene / cumple una expresión, el monto está en un rango, el banco o el tercero coinciden → cuenta(s) con monto fijo, porcentaje o tomado del texto; o solo asignar el tercero. «Automático» = se concilia sola al importar. (Reglas con impuestos: fase 2.) |
| **Bancos › Formatos de extracto (CSV)** | Para el CSV de un banco que no se reconoce solo: columnas por nombre o número (varias unidas con «+»), filas de título, coma decimal, codificación Windows, cargos/abonos, signo invertido. Se elige solo al importar en ese banco. |
| **Reportes contables › Resumen contable** | Para la dueña: dinero en cada banco/caja (y cuánto falta conciliar), te deben / debes (con lo vencido), ITBMS del periodo, ventas y utilidad contra el periodo anterior, quién te debe más y alertas. Cada tarjeta lleva a su detalle. |
| **Reportes contables** | Estado de resultados, Balance general, **Flujo de efectivo** (método indirecto; cuadra con los bancos), **Por cobrar** y **Por pagar** (antigüedad por tramos a una fecha de corte), Balance de comprobación, Libro mayor, Resumen de ITBMS y Rentabilidad analítica. Atajos de periodo, **comparar con el periodo anterior o el año pasado** (ER, balance y flujo), detalle hasta el asiento, «incluir borradores», exportación a Excel y PDF. |
| **Reportes contables › Presupuestos** | Monto planeado por cuenta contable (y cuenta analítica, opcional); lo real y el % ejecutado salen de los asientos. |
| **Cierre de mes** | Lista de chequeo con datos reales (bancos conciliados, borradores, ventas por facturar, comprobación y balance que cuadran, cobros vencidos, ITBMS, meses anteriores). Si nada lo impide, la gerencia contable **cierra el mes**: fija la fecha de bloqueo de Odoo (y la de ITBMS si se marca) y nadie puede publicar ni cambiar asientos de ese mes. Reabrir pide motivo y queda en el historial. |
| **Plan contable › cuenta › Actividad en el flujo de efectivo** | Para que el contador ubique una cuenta especial (p. ej. un préstamo de corto plazo → financiamiento). Vacío = según el tipo de cuenta. |
| **Cheques** | Formato «Cheque D'CASA» con el monto en letras en español («Mil Doscientos Cincuenta Dólares con 50/100») y talón con las facturas pagadas. Pago de proveedor → método «Cheque» en el diario Banco → Imprimir cheque. |
| **Analítica** | Plan «Canal de venta» con «Tienda física (La Chorrera)» y «Tienda en línea». Se elige en la columna Analítica de cada línea de factura. |

Los reportes solo los ve quien tiene permisos de contabilidad (grupo «Mostrar
funciones de contabilidad: solo lectura» o superior).

## Usuarios

Odoo Community no limita la cantidad de usuarios: se crean todos los que hagan falta
(Ajustes › Usuarios). El cobro «por usuario» es de Odoo Enterprise/Odoo.sh, que D'CASA
no usa.

## En desarrollo (con su plan)

- **Nómina y reembolsos en nómina**: fichas de colaboradores, planilla quincenal
  (seguro social, seguro educativo, ISR), décimo tercer mes, vacaciones y asiento
  automático. Necesita las tasas y reglas vigentes validadas por el contador.
- **Facturación electrónica DGI (SFEP)**: exige contrato con un PAC autorizado; el envío
  de cada factura, el CUFE y el QR se integran con la API del PAC elegido.
- **Consolidación**: solo aplica si D'CASA llega a tener más de una empresa
  (multiempresa ya viene incluido en Community).

## Brian

Lectura (grupo de contabilidad): `resumen_contable` («¿cuánto gané este mes?», «¿cuánto ITBMS
debo?»), `antiguedad_saldos` («¿quién me debe?»), `comparar_periodos`, `reporte_contable`
(incluye el flujo de efectivo) y `guia_cierre_mes`. **Sensible** (la gerencia contable confirma
con un clic): `cerrar_mes`.

## Plan

Brechas con Enterprise, fases siguientes y lo que **requiere contador**:
`docs/auditoria/ronda6/contabilidad-plan.md`.

## Pruebas

`scripts/test.sh dcasa_contabilidad`: el balance de comprobación cuadra, la ecuación
contable del balance general se cumple, el ITBMS (débito − crédito) coincide con las
facturas, la conciliación con factura, parcial, con cuenta de gasto y automática,
la importación de CSV sin duplicados, el presupuesto (real y %), el cheque en letras y
los permisos. Fase 1 (`tests/test_fase1.py`): comparativos (periodos y variaciones), flujo
de efectivo que cuadra con los bancos (también con depreciación y actividad elegida),
antigüedad a fecha de corte que coincide con el saldo contable, resumen, cierre de mes con
bloqueo y reapertura, reglas de conciliación (automática, manual, de tercero) y extractos
CSV con formato, OFX y CAMT sin duplicar.
