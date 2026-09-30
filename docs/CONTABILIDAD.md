# Contabilidad de D'CASA (`dcasa_contabilidad`)

Construida sobre la contabilidad de Odoo 19 Community (partida doble, plan contable
de Panamá `l10n_pa`, ITBMS). Todo sale de los asientos publicados: no hay cifras
guardadas aparte.

## Qué hay (menú Facturación)

| Menú | Qué hace |
|---|---|
| **Bancos › Conciliación bancaria** | Movimientos del banco sin explicar a la izquierda; a la derecha, las facturas y pagos que los explican (sugeridos por monto, cliente y referencia) o una cuenta para comisiones y cargos. Conciliación parcial, automática (solo lo inequívoco) y «deshacer». Una pestaña por banco: Banco, Tarjeta, Yappy, Efectivo. |
| **Bancos › Importar extracto** | CSV de la banca en línea (Banco General, BAC, Banistmo, Caja de Ahorros, Yappy…). Reconoce Fecha, Descripción, Monto o Débito/Crédito, Referencia; separador `,` o `;`; montos `1,234.56`, `1.234,56` o `(45.00)`. No duplica lo ya importado y concilia solo lo seguro. |
| **Reportes contables** | Estado de resultados, Balance general, Balance de comprobación, Libro mayor, Resumen de ITBMS y Rentabilidad analítica. Atajos de periodo, detalle hasta el asiento, «incluir borradores», exportación a Excel y PDF. |
| **Reportes contables › Presupuestos** | Monto planeado por cuenta contable (y cuenta analítica, opcional); lo real y el % ejecutado salen de los asientos. |
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

## Pruebas

`scripts/test.sh dcasa_contabilidad`: el balance de comprobación cuadra, la ecuación
contable del balance general se cumple, el ITBMS (débito − crédito) coincide con las
facturas, la conciliación con factura, parcial, con cuenta de gasto y automática,
la importación de CSV sin duplicados, el presupuesto (real y %), el cheque en letras y
los permisos.
