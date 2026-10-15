# Contabilidad de D'CASA (`dcasa_contabilidad`)

Construida sobre la contabilidad de Odoo 19 Community (partida doble, plan contable
de Panamá `l10n_pa`, ITBMS). Todo sale de los asientos publicados: no hay cifras
guardadas aparte.

## Qué hay (menú Facturación)

| Menú | Qué hace |
|---|---|
| **Bancos › Conciliación bancaria** | Movimientos del banco sin explicar a la izquierda; a la derecha, las facturas y pagos que los explican (sugeridos por monto, cliente y referencia) o una cuenta para comisiones y cargos. Conciliación parcial, automática (solo lo inequívoco) y «deshacer». Arriba, las **reglas que aplican** al movimiento, con un clic. Una pestaña por banco: Banco, Tarjeta, Yappy, Efectivo. Si hay **cobros o pagos registrados con «Registrar pago» que todavía no tienen su movimiento** en ese diario (típico del efectivo), la lista lleva una segunda pestaña, **«Cobros y pagos sin movimiento»**: cada uno se ve con su factura y su monto y el botón **«Crear el movimiento y cruzar»** registra la entrada o salida en la caja o el banco y la cruza con el cobro. En un banco pide confirmar (si luego importas el extracto, ese movimiento llegaría repetido: lo normal es importar y conciliar desde «Movimientos del extracto»). Si el mes de la fecha del pago ya está cerrado, el movimiento lleva el primer día abierto. |
| **Bancos › Importar extracto** | **CSV** de la banca en línea (Banco General, BAC, Banistmo, Caja de Ahorros, Yappy…), **OFX/QFX** o **CAMT.053**. En CSV reconoce Fecha, Descripción, Monto o Débito/Crédito, Referencia aunque haya filas de título arriba; separador y codificación se detectan; montos `1,234.56`, `1.234,56`, `(45.00)` o `45.00-`. **Vista previa** antes de importar. No duplica lo ya importado (por el identificador del banco en OFX/CAMT), avisa si el saldo final del banco no coincide y concilia solo lo seguro. |
| **Bancos › Reglas de conciliación** | Las reglas de Odoo (`account.reconcile.model`) con motor propio: si la descripción contiene / no contiene / cumple una expresión, el monto está en un rango, el banco o el tercero coinciden → cuenta(s) con monto fijo, porcentaje o tomado del texto; o solo asignar el tercero. «Automático» = se concilia sola al importar. (Reglas con impuestos: fase 2.) |
| **Bancos › Formatos de extracto (CSV)** | Para el CSV de un banco que no se reconoce solo: columnas por nombre o número (varias unidas con «+»), filas de título, coma decimal, codificación Windows, cargos/abonos, signo invertido. Se elige solo al importar en ese banco. |
| **Reportes contables › Resumen contable** | Para la dueña: dinero en cada banco/caja (y cuánto falta conciliar), te deben / debes (con lo vencido), ITBMS del periodo, ventas y utilidad contra el periodo anterior, quién te debe más y alertas. Cada tarjeta lleva a su detalle y **dice de qué fecha es** («al 14 oct» si es un saldo; «del 1 al 14 oct» si es lo que pasó en el periodo). Ver [Cómo leer las fechas](#cómo-leer-las-fechas-saldos-y-movimientos). |
| **Reportes contables** | Estado de resultados, Balance general, **Flujo de efectivo** (método indirecto; cuadra con los bancos), **Por cobrar** y **Por pagar** (antigüedad por tramos a una fecha de corte), Balance de comprobación, Libro mayor, Resumen de ITBMS y Rentabilidad analítica. Atajos de periodo (**Hoy · Esta semana · Esta quincena · Este mes · Mes pasado · Este trimestre · Este año fiscal**, el que está activo se ve resaltado; al escribir una fecha a mano ninguno queda marcado), **comparar con el periodo anterior o el año pasado** (ER, balance y flujo), detalle hasta el asiento, «incluir borradores», exportación a Excel y PDF. |
| **Reportes contables › Presupuestos** | Monto planeado por cuenta contable (y cuenta analítica, opcional) para un periodo (un mes, un trimestre, un año…). Lo **real** sale de los asientos publicados de la cuenta en ese periodo (los borradores y cancelados no cuentan; una nota de crédito resta). Cada línea dice cuánto **queda por ejecutar**, el **% ejecutado** y su **situación**: un gasto se vigila contra un tope («Dentro» / «Te pasaste») y un ingreso contra una meta («En camino» / «Meta cumplida»); con planeado en cero dice «Sin presupuesto» en vez de un 0 %. Los totales separan **ingresos, gastos y resultado** (las cuentas de balance no entran) y una línea por canal que es parte de otra de la misma cuenta no se suma dos veces. «Tiempo transcurrido» sirve para comparar el % ejecutado con lo que ya pasó del periodo. En la lista, filtros por estado y por el **periodo que tocan** (Hoy · Esta semana · Esta quincena · Este mes · Mes pasado · Este trimestre · Este año fiscal). |
| **Cierre de mes** | Lista de chequeo con datos reales (bancos conciliados —movimientos del extracto **y** cobros o pagos registrados que esperan su movimiento, con cuántos y de cuánto—, borradores, ventas por facturar, comprobación y balance que cuadran, cobros vencidos, ITBMS, meses anteriores). Si nada lo impide, la gerencia contable **cierra el mes**: fija la fecha de bloqueo de Odoo (y la de ITBMS si se marca) y nadie puede publicar ni cambiar asientos de ese mes. Reabrir pide motivo y queda en el historial. |
| **Plan contable › cuenta › Actividad en el flujo de efectivo** | Para que el contador ubique una cuenta especial (p. ej. un préstamo de corto plazo → financiamiento). Vacío = según el tipo de cuenta. |
| **Cheques** | Formato «Cheque D'CASA» con el monto en letras en español («Mil Doscientos Cincuenta Dólares con 50/100») y talón con las facturas pagadas. Pago de proveedor → método «Cheque» en el diario Banco → Imprimir cheque. |
| **Analítica** | Plan «Canal de venta» con «Tienda física (La Chorrera)» y «Tienda en línea». Se elige en la columna Analítica de cada línea de factura. |

Los reportes solo los ve quien tiene permisos de contabilidad (grupo «Mostrar
funciones de contabilidad: solo lectura» o superior).

## Cómo leer las fechas: saldos y movimientos

Toda la barra de periodo es una sola para los diez reportes. Hay **dos clases de cifra** y la pantalla dice cuál es cada una:

| Clase | Qué es | Qué fecha usa | Ejemplos |
|---|---|---|---|
| **Saldo** (a una fecha) | Cuánto hay o cuánto se debe en ese día | Solo el **«Hasta»** (en esos reportes se llama «Al»). Mover el «Desde» no lo cambia | Dinero en bancos y caja, Te deben, Debes, Vencido, **ITBMS acumulado / Saldo a favor**, Balance general, Por cobrar, Por pagar, saldo final del balance de comprobación y del libro mayor |
| **Movimiento** (de un periodo) | Lo que pasó entre dos fechas | «Desde» y «Hasta» | Ventas, Utilidad, ITBMS del periodo (ventas − compras), Estado de resultados, Flujo de efectivo, movimiento del libro mayor, Analítica |

Por eso **«Dinero en bancos y caja» no cambia con «Este mes»**: es un saldo y «Este mes», «Este trimestre», «Esta quincena», «Esta semana», «Hoy» y «Este año fiscal» terminan todos hoy. Cambia con «Mes pasado» (al último día de ese mes) o al escribir otra fecha «Hasta». **Lo vencido** se mide contra esa misma fecha: una factura que vence el 3 no está vencida «al 30 del mes anterior».

Los atajos (hora de Panamá, `America/Panama`; la del usuario si tiene otra configurada) **terminan hoy**, menos «Mes pasado». Son los mismos en los reportes, en el formulario de Consolidación (elige uno y se llenan el «Desde» y el «Hasta») y como filtros de las listas de Presupuestos y Consolidación, donde muestran lo que **toca** ese periodo (un presupuesto de todo el año sale en «Este mes»; uno que empieza mañana no, porque el atajo termina hoy):

| Atajo | Desde → hasta |
|---|---|
| Hoy | hoy → hoy |
| Esta semana | el lunes (la semana va de lunes a domingo) → hoy |
| Esta quincena | el día 1 (del 1 al 15) o el 16 (del 16 a fin de mes) → hoy |
| Este mes | día 1 → hoy |
| Mes pasado | día 1 → último día del mes pasado |
| Este trimestre | primer día del trimestre del año fiscal → hoy |
| Este año fiscal | primer día del año fiscal → hoy (el cierre fiscal es el de la empresa, 31 de diciembre) |

Para ver el año completo (o una fecha futura) se escribe el «Hasta» a mano; la pantalla avisa que esa fecha todavía no llega. Una fecha «Desde» posterior a «Hasta» se corrige sola en la pantalla y en el servidor da un error claro. «Comparar» compara «Hoy» con ayer, una semana o quincena con los días justo antes (o, si empieza el día 1, con el mismo tramo del mes anterior) y el balance general, que es de una fecha, con la misma fecha un mes antes (o un año antes).

**ITBMS: periodo y acumulado.** La tarjeta «ITBMS por pagar» del Resumen y el reporte **Resumen de ITBMS** muestran las dos cosas, cada una con su fecha: lo **del periodo** (ventas − compras, «del 1 al 14 oct») y el **acumulado «al 14 oct»**, que es el saldo de la cuenta de ITBMS hasta el «Hasta», medido igual que el Balance general (solo asientos publicados): suma los meses anteriores y descuenta lo que ya se pagó. Si lo que se pagó o las compras superan a las ventas, el acumulado es un **«Saldo a favor»** (en verde, con ese nombre; nunca un negativo en «por pagar»). La cuenta o cuentas de ITBMS salen de la configuración de los impuestos de venta y compra (la cuenta de su reparto «de impuesto»); el reporte las lista con su saldo. Las retenciones de ITBMS no se tocan: en el plan instalado no hay cuenta ni impuesto de retención de ITBMS (la única «Retenciones a depositar», 2440000, es de salarios).

«**Todo conciliado**» en la tarjeta del banco —y el paso «Bancos, Yappy, tarjeta y caja conciliados» del Cierre de mes y la guía de cierre de Brian, que usan la misma cuenta (`dcasa.cierre.mes._bancos_por_cruzar`, sobre `_saldos_bancos`)— significa que no queda ningún movimiento del extracto sin conciliar **ni cobro o pago registrado** (en la factura, con «Registrar pago») esperando su movimiento del banco o de la caja: esos cobros y pagos esperan en «Recibos pendientes» / «Pagos pendientes» y no suman al dinero del banco hasta que se cruzan. Cuando hay algo por cruzar, la tarjeta dice cuántos y de cuánto.

La auditoría completa (qué se revisó, qué se encontró y qué le preguntamos a la contadora) está en [AUDITORIA_CONTABLE.md](AUDITORIA_CONTABLE.md).

## Usuarios

Odoo Community no limita la cantidad de usuarios: se crean todos los que hagan falta
(Ajustes › Usuarios). El cobro «por usuario» es de Odoo Enterprise/Odoo.sh, que D'CASA
no usa.

## Nómina, consolidación y lo que sigue en desarrollo

- **Nómina y reembolsos en nómina**: ya están construidos en `dcasa_nomina` (menú **Nómina**; guía en
  [docs/NOMINA.md](NOMINA.md)): fichas de colaboradores, planilla quincenal (seguro social, seguro educativo e ISR),
  décimo tercer mes, vacaciones, prima, liquidación y asiento automático. Las tasas de la ley las **valida el
  contador** antes de poder confirmar una planilla.
- **Consolidación**: construida en `dcasa_consolidacion` (Facturación › Reportes contables › Consolidación; guía en
  [docs/CONSOLIDACION.md](CONSOLIDACION.md)): estados financieros de varias empresas con eliminaciones entre ellas.
- **Facturación electrónica DGI (SFEP)**: sigue **en desarrollo** (pantalla «En desarrollo»): exige contrato con un PAC
  autorizado; el envío de cada factura, el CUFE y el QR se integran con la API del PAC elegido
  (`dcasa_fe_pa`, [docs/FACTURA_ELECTRONICA.md](FACTURA_ELECTRONICA.md)).

## Brian

Lectura (grupo de contabilidad): `resumen_contable` («¿cuánto gané este mes?», «¿cuánto ITBMS
debo este mes?» y «¿cuánto ITBMS debo en total?»: da lo del periodo y, aparte, el **acumulado por pagar o saldo a favor** a la fecha final), `antiguedad_saldos` («¿quién me debe?»), `comparar_periodos`, `reporte_contable`
(incluye el flujo de efectivo) y `guia_cierre_mes` (cuenta también los cobros y pagos que esperan su movimiento) y `movimientos_por_conciliar` (movimientos del extracto **y** cobros y pagos sin cruzar, cuántos y de cuánto; solo los muestra). `reporte_contable` con `itbms` trae igual el acumulado y el saldo de cada cuenta de ITBMS. **Sensible** (la gerencia contable confirma
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
Auditoría de los reportes (`tests/test_auditoria.py`, con datos de `tests/datos_auditoria.py` y el cálculo independiente en SQL de `tests/oraculo_sql.py`): cada reporte y cada tarjeta se cruza contra los apuntes publicados para un día, la semana, el mes, el año, un periodo que cruza el cierre fiscal y varias fechas de corte; los atajos de fechas se prueban en sus bordes (semana que cruza mes y año, quincena de febrero, año bisiesto, otro cierre fiscal, hora de Panamá contra UTC) y hay una prueba con dos empresas. Cómo repetirlo: `scripts/test.sh dcasa_contabilidad`.
Presupuestos (`tests/test_presupuesto.py`, con `tests/oraculo_presupuesto.py`): lo real de cada línea se cruza contra los apuntes publicados en 9 periodos × 9 tipos de línea (ingreso, gasto, dos canales, banco, préstamo, capital, mobiliario), con cifras a mano (nota de crédito que resta, borradores y cancelados fuera, periodo parcial), planeado en cero, color de ingreso contra gasto, totales sin doble conteo, tiempo transcurrido, dos empresas y los atajos de fechas de la lista en sus fechas borde.
Cierre y conciliación (`tests/test_cierre_conciliacion.py`): el paso de bancos del cierre, la tarjeta del Resumen y la pantalla de Conciliación ven lo mismo (contra un conteo aparte en SQL); un cobro de caja registrado y sin cruzar ya no pasa como «Todo conciliado» y se puede cruzar desde la pantalla (también un pago a proveedor, y con el mes cerrado). La guía de cierre de Brian tiene su prueba en `dcasa_brian/tests/test_herramientas_contabilidad.py`.
Pantallas propias (`tests/test_pantallas.py`): reportes, conciliación y «En desarrollo» comparten la raíz
`.o_dc_conta.o_action`; Odoo pone a todo `.o_action` en columna con `overflow: hidden`, así que sin la regla propia de
`contabilidad.scss` la pantalla no baja y la barra de pestañas se aplasta. La prueba vigila esa regla (se comprobó en un
navegador con una tabla de 2,500 px).
