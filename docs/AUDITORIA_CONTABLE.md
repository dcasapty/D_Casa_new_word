# Auditoría de los reportes contables

Revisión de los diez reportes de **Facturación › Reportes contables** (Resumen, Estado de resultados, Balance general,
Flujo de efectivo, Por cobrar, Por pagar, Balance de comprobación, Libro mayor, Resumen de ITBMS y Analítica), de sus
filtros de fechas y de lo que dice cada tarjeta. Módulo: `dcasa_contabilidad` (guía de uso: [CONTABILIDAD.md](CONTABILIDAD.md)).

Hecha el 14 de octubre de 2026. Los números de los ejemplos son **datos de prueba**, no de la empresa.

## En pocas palabras

* **Las cuentas estaban bien hechas.** Se armaron datos como los de una mueblería (facturas pagadas, a medias, vencidas,
  por vencer, en borrador y canceladas; notas de crédito de clientes y de proveedores; cobros por banco, caja y Yappy;
  gastos con y sin ITBMS; capital, mobiliario y préstamos) y cada reporte se comparó, cifra por cifra, contra un
  cálculo hecho aparte directamente sobre los apuntes contables. Coincidieron: el balance cuadra, el balance de
  comprobación cuadra, el flujo de efectivo explica exactamente lo que cambió en el banco y la caja, y las facturas
  en borrador o canceladas nunca cuentan.
* **Lo que fallaba eran los filtros y la forma de nombrar las cifras.** Se encontraron 8 problemas, todos arreglados
  (sección «Hallazgos»). Los dos que la dueña notó están explicados abajo.
* **Quedan 9 preguntas para la contadora** (sección «Para la contadora»; en dos la dueña ya decidió una parte). Ninguna se decidió sin ella.

## La duda de la dueña: ¿«Dinero en bancos y caja» debería cambiar con «Este mes»?

**Depende de la fecha «Hasta», no de la «Desde».** «Dinero en bancos y caja» es un **saldo**: cuánto hay en ese día.
Un saldo no tiene principio, solo tiene un día. Entonces:

| Filtro | Hasta | Dinero en bancos y caja (datos de prueba) |
|---|---|---|
| Hoy, Esta semana, Esta quincena, Este mes, Este trimestre, Este año fiscal | 14 oct (hoy) | $26,742.50 |
| Mes pasado | 30 sep | $25,348.00 |

Los seis primeros terminan hoy, por eso dan lo mismo: está bien que no cambie. Cambia en cuanto cambia el «Hasta»
(«Mes pasado», o una fecha escrita a mano). Lo que **no estaba bien** es que la tarjeta no decía de qué fecha era;
ahora dice **«AL 14 OCT»**. En cambio **Ventas, Utilidad e ITBMS** son movimientos del periodo y sí cambian con el
«Desde» (la tarjeta dice «DEL 1 AL 14 OCT»).

También cuadra entre pantallas: el dinero de la tarjeta es igual al efectivo del Balance general al mismo día y al
«Efectivo al final» del Flujo de efectivo.

## Cómo se mide cada cifra

| Reporte o tarjeta | Es un… | Fechas que usa |
|---|---|---|
| Dinero en bancos y caja | saldo | hasta «Hasta» |
| Te deben · Debes a proveedores | saldo | lo pendiente de cada factura al «Hasta» (un pago hecho después no cuenta) |
| Vencido | saldo | lo pendiente cuya fecha de pago es anterior al «Hasta» |
| Balance general | saldo | al «Hasta» (el «Desde» no se usa) |
| Por cobrar · Por pagar | saldo | al «Hasta»: tramos por días vencidos contra esa fecha |
| Balance de comprobación | los dos | saldo inicial = antes del «Desde»; debe y haber = del periodo; saldo final = al «Hasta» |
| Libro mayor | los dos | saldo inicial + movimientos del periodo = saldo final |
| Estado de resultados · Ventas · Utilidad | movimiento | del «Desde» al «Hasta» |
| ITBMS del periodo (tarjeta y reporte) | movimiento | del periodo: ventas − compras |
| ITBMS acumulado / Saldo a favor (tarjeta y reporte) | saldo | saldo de la cuenta de ITBMS al «Hasta»: meses anteriores y pagos incluidos |
| Flujo de efectivo | movimiento | variación del efectivo del periodo; inicio = día anterior al «Desde», final = «Hasta» |
| Analítica | movimiento | del periodo |

## Los atajos de fechas

Todos con la hora de Panamá: **Hoy · Esta semana · Esta quincena · Este mes · Mes pasado · Este trimestre · Este año
fiscal**. Detalle en [CONTABILIDAD.md](CONTABILIDAD.md#cómo-leer-las-fechas-saldos-y-movimientos). Decisiones tomadas:

* La **semana** va de lunes a domingo; el atajo muestra de lunes a hoy.
* La **quincena** es del 1 al 15 o del 16 a fin de mes (febrero de 28 o 29 días incluido); el atajo muestra desde el 1 o
  el 16 hasta hoy.
* **Todos terminan hoy** (menos «Mes pasado»), como «Este mes» ya lo hacía. Así un saldo nunca queda con una fecha que
  aún no llega.
* El **trimestre** se cuenta desde el inicio del año fiscal de la empresa (hoy 31 de diciembre, o sea ene-mar, abr-jun…).

## Hallazgos

Cada uno dice qué estaba mal, un ejemplo con números de prueba y cómo quedó.

**H1. «Todo conciliado» engañaba.**
*Qué estaba mal:* solo miraba los movimientos del extracto del banco sin conciliar. Un cobro registrado en la factura
con «Registrar pago» (en efectivo, banco o Yappy) no entra al dinero del banco hasta que se cruza con su movimiento: queda
en «Recibos pendientes», y la tarjeta no lo veía. *Ejemplo:* abono de $200 en efectivo registrado en una factura, sin
movimiento de caja. Con el depósito suelto ya conciliado, la tarjeta habría dicho «Todo conciliado» y $200 estaban en el
cajón sin aparecer en ningún lado. Además decía «1 movimientos» (plural).
*Cómo quedó:* «Todo conciliado» solo sale si no hay ni movimientos del banco sin conciliar ni cobros o pagos esperando su
movimiento. Si hay, la tarjeta dice cuántos y de cuánto («1 movimiento por conciliar», «1 cobro sin cruzar: $200.00»), hay
una alerta y cada banco muestra su cuenta. **Qué mide:** lo que **hoy** sigue sin cruzar y tiene fecha hasta el corte.

**H2. «Este año fiscal» terminaba en el futuro.**
*Qué estaba mal:* terminaba el 31 de diciembre. Los saldos y lo vencido se medían contra una fecha que todavía no llega:
al elegir «Este año fiscal» las facturas que vencen en los días que vienen ya salían vencidas. *Ejemplo:* «Te deben» $2,614.50
con «Vencido» $2,154.00 el 14 oct; con el corte al 31 dic salía «Vencido» $2,614.50 (todo). «Debes» subía de $938.10
a $1,038.10 por un gasto fechado el 20 oct. *Cómo quedó:* «Este año fiscal» va del inicio del año fiscal hasta hoy, igual que
Este mes y Este trimestre. Para ver el año completo se escribe el «Hasta»; si la fecha todavía no llega, la pantalla avisa
que lo vencido se mide contra esa fecha.

**H3. El libro mayor daba mal el saldo final de una cuenta con muchos movimientos.**
*Qué estaba mal:* la pantalla muestra a lo sumo 2,000 movimientos por cuenta, pero el debe, el haber y el **saldo final** se
sumaban solo sobre los movimientos mostrados. *Ejemplo:* Banco del 1 ene al 14 oct, recortado a 3 movimientos: decía saldo
final $18,348.00; el correcto es $26,584.50. El Excel y el PDF también salían recortados sin avisar. *Cómo quedó:* el saldo
inicial, el debe, el haber y el saldo final salen siempre de la suma completa (saldo inicial + movimientos = saldo final);
solo se recorta el detalle, y el Excel y el PDF llevan todos los movimientos.

**H4. Comparar el balance general podía comparar contra una fecha absurda.**
*Qué estaba mal:* el balance es «a una fecha» y no muestra el «Desde», pero la comparación usaba ese «Desde» escondido.
*Ejemplo:* con el «Desde» escondido en 1 oct y «Al» 31 mar, comparaba contra el 30 sep (más tarde que la fecha elegida).
*Cómo quedó:* el balance se compara con la misma fecha un mes antes (o un año antes) y el fin de mes sigue siendo fin de mes
(31 mar → 28 feb). El comparativo dice la fecha exacta.

**H5. Fechas al revés daban ceros sin avisar.**
*Qué estaba mal:* con «Desde» después de «Hasta» el reporte salía vacío, como si no hubiera movimientos. *Cómo quedó:* en la
pantalla la otra fecha se corrige sola; en el servidor (Excel, PDF, Brian) sale un mensaje claro.

**H6. «Hoy» podía ser mañana.**
*Qué estaba mal:* el servidor trabaja en hora UTC, que a las 7 p. m. de Panamá ya es el día siguiente: «Hoy» y todo lo que
se mide contra hoy (lo vencido, el periodo por defecto) salían un día adelantados por la noche. *Cómo quedó:* «hoy» se
calcula en la zona de la persona o, si no tiene una configurada, en `America/Panama`. No depende de la hora de la computadora.

**H7. Rentabilidad analítica: ingresos y costos mal clasificados y ventas sin canal invisibles.**
*Qué estaba mal:* clasificaba por el signo del monto: una nota de crédito de venta salía como «costo». Y lo que no se
asignaba a ningún canal no aparecía, así que el total de los canales no cuadraba con el Estado de resultados sin que
nadie lo supiera. *Ejemplo:* ventas del 1 al 14 oct $1,800.00; la suma de los canales daba $1,650.00 (faltaban
$150.00 de una venta sin canal) y a los costos les faltaban $460.00 de gastos sin canal. *Cómo quedó:* se clasifica por
el tipo de cuenta (ingreso o gasto) y hay una fila **«Sin asignar»**; las filas del canal más «Sin asignar» suman lo mismo
que el Estado de resultados. Recomendación: elegir el canal en cada línea de venta.

**H8. «Otras cuentas de efectivo» no entraban a la tarjeta.**
*Qué estaba mal:* la tarjeta sumaba solo las cuentas de los diarios de banco y caja; el Balance general y el Flujo suman
**todas** las cuentas de tipo efectivo. Si alguna vez existe una cuenta de efectivo sin diario, las pantallas no coincidirían.
*Cómo quedó:* esa cuenta aparece como «Otras cuentas de efectivo» y la tarjeta coincide siempre con el Balance y el Flujo.

**Mejoras de claridad (no eran errores de cálculo):**
* Cada tarjeta y cada indicador dice su fecha («AL 14 OCT», «DEL 1 AL 14 OCT», «EL 14 OCT»); el Resumen explica abajo la
  diferencia entre saldos y movimientos.
* **ITBMS: periodo y acumulado.** «ITBMS por pagar» era lo del **periodo** (ventas − compras), no lo que se debe en total: la cuenta
  «ITBMS a pagar» del Balance suma meses anteriores sin pagar ($298.90 contra $99.40 del 1 al 14 oct en los datos de prueba).
  Por pedido de la dueña, la tarjeta del Resumen y el reporte de ITBMS muestran las dos cosas con su fecha: lo del periodo
  («DEL 1 AL 14 OCT») y el **acumulado por pagar «AL 14 OCT»**. Si queda a favor se llama **«Saldo a favor»** y se ve en verde.
  El acumulado se calcula como el Balance general (solo asientos publicados), cambia con «Hasta» y no con «Desde», baja cuando se
  registra un pago de ITBMS y las notas de crédito restan. Las cuentas salen de los impuestos configurados y el reporte las lista.
* Excel y PDF: un día solo dice «El 14/10» (antes «Al»); el Resumen lleva una columna «Fecha o periodo».
* «Hoy» se compara con ayer (también el día 1 del mes).
* El balance de comprobación avisa si el periodo cruza el cierre del año fiscal (ver «Límites conocidos»).
* El detalle de ITBMS respeta «Incluir borradores» al abrir los apuntes.
* En lo vencido se pueden ver negativos: son notas de crédito o anticipos sin aplicar (pregunta C6).

## Lo que se revisó y estaba bien

Contra el cálculo independiente, en 9 periodos distintos (un día, la semana, el mes, el mes pasado, el año a hoy, el año
completo, un periodo que cruza el cierre del año fiscal, el año anterior y uno a mitad de mes) y 11 fechas de corte:

* **Balance general:** activo = pasivo + patrimonio en todas las fechas; el resultado del ejercicio en curso es la utilidad
  del año fiscal hasta esa fecha y lo de años anteriores va aparte; cada cuenta es su saldo acumulado.
* **Balance de comprobación:** debe = haber; saldo inicial + movimiento = saldo final en cada cuenta; los totales de saldo inicial
  y final son cero; los resultados de años anteriores se muestran en su propia fila.
* **Estado de resultados:** ventas, costo, gastos, depreciación, otros ingresos y otros gastos coinciden con los apuntes; no cuentan
  borradores, cancelados ni lo fechado después del «Hasta»; el costo se muestra aparte de los gastos.
* **Flujo de efectivo:** la variación es exactamente lo que cambió el efectivo; cada actividad coincide con el cálculo aparte.
* **Por cobrar y Por pagar:** la antigüedad se mide contra el «Hasta»; los pagos parciales se restan solo si son anteriores al
  corte; las notas de crédito restan; los borradores y cancelados no entran; el total es el saldo de las cuentas por cobrar o
  por pagar del Balance; con corte en el futuro coincide con lo que Odoo dice que falta pagar de cada factura.
* **ITBMS:** base e impuesto por tasa, ventas y compras por separado, las notas de crédito restan, la venta exenta aparece
  con su base y sin impuesto; se usan los impuestos configurados (no hay tarifas escritas en el código). El acumulado coincide con
  el saldo de la cuenta de ITBMS en el Balance general en 11 fechas de corte, con pagos, notas de crédito y saldo a favor.
* **Libro mayor:** saldo inicial + movimientos = saldo final (con el detalle completo y recortado).
* **Dos empresas:** cada reporte lee solo las empresas activas; juntas suman y cada una por separado cuadra.

## Para la contadora

Nada de esto se decidió sin ella; cada una afecta cómo se ve un reporte.

* **C1. Activo fijo e intangibles como «corriente».** El plan contable de Panamá instalado trae las cuentas 1610000 a 1650000 (activo
  fijo y su depreciación acumulada) y 1710000 a 1740000 (intangibles) como **activo corriente**. ¿Se cambian a activo no
  corriente? Cambia el Balance general y el Flujo (lo que hoy es «operación» pasaría a «inversión»).
* **C2. Anticipos de clientes.** La cuenta 2120000 «Anticipos de Cliente» es de tipo «por pagar». Un anticipo de un cliente
  saldría en «Debes a proveedores». ¿Se usa esa cuenta? ¿Cómo se quiere llevar un anticipo?
* **C3. Préstamos.** La cuenta 2220000 «Préstamos» es pasivo corriente. ¿Son de corto o de largo plazo? ¿Se marcan como
  «financiamiento» en el flujo (se hace en el plan contable, campo «Actividad en el flujo de efectivo»)?
* **C4. ITBMS.** *Decisión de la dueña:* quiere ver, además de lo del periodo, el **acumulado por pagar al «Hasta»** y el **saldo
  a favor**. Ya está (ver «Mejoras»). Queda por preguntar a la contadora: ¿cómo se maneja el saldo a favor que pasa de un mes
  al siguiente en la declaración? Las **retenciones de ITBMS** no se tocaron: el plan instalado no trae cuenta ni impuesto de
  retención de ITBMS (la cuenta «Retenciones a depositar», 2440000, es de salarios). Si la empresa las usa, ¿en qué cuenta
  se llevan?
* **C5. Dinero en tránsito.** *Decisión de la dueña:* los cobros registrados que el banco aún no confirma **se quedan aparte**
  (no suman al «Dinero en bancos y caja»; se muestran como «sin cruzar»). Solo queda saber cómo se quiere llevar el efectivo de
  la caja: ¿un movimiento de caja por cada cobro o el saldo directo?
* **C6. Notas de crédito y anticipos sin aplicar.** En «Por cobrar» y «Por pagar» salen en negativo dentro de su tramo y
  restan del vencido. ¿Se muestran aparte, como «a favor»?
* **C7. Cierre anual.** El cierre de mes solo bloquea fechas. Si algún día se hace un asiento de cierre que pasa los
  resultados al patrimonio, el Estado de resultados de ese año quedaría en cero. ¿Cómo se hará el cierre anual?
* **C8. Costo de ventas.** Mientras los productos no tengan costo, el margen sale casi 100 %. ¿Cuándo se cargan los costos?
* **C9. Moneda.** Los reportes suman las empresas activas sin convertir monedas. Si alguna empresa del grupo usa otra
  moneda, hay que verlo con la Consolidación. ¿Hay alguna?

Y una confirmación: la empresa tiene el año fiscal terminando el **31 de diciembre**; de ahí salen «Este año fiscal» y el
trimestre. ¿Es correcto?

## Límites conocidos

* **Balance de comprobación entre dos años fiscales** (por ejemplo del 29 dic al 3 ene, lo que pasa con «Esta semana» en esos
  días): las cuentas de resultados siguen acumulando desde el inicio del año fiscal de la fecha «Desde» (no se «reinician» a
  medio periodo). Sigue cuadrando y la pantalla lo avisa. El Balance general sí separa bien el año.
* «Comparar» no existe en Por cobrar, Por pagar, Balance de comprobación, Libro mayor, ITBMS ni Analítica (solo en Estado de
  resultados, Balance general y Flujo).
* «Por conciliar» muestra lo que **hoy** falta cruzar con fecha hasta el corte; no reconstruye el estado de ayer.
* La analítica solo ve asientos publicados (las líneas analíticas se crean al publicar): «Incluir borradores» no la cambia.
* Con varias empresas activas a la vez, los reportes suman todas y usan el año fiscal de la empresa principal.

## Cómo se probó

* `tests/test_auditoria.py` (52 pruebas) usa los datos de `tests/datos_auditoria.py` y un cálculo hecho aparte, directo en
  SQL sobre los apuntes publicados, que no usa el motor de los reportes (`tests/oraculo_sql.py`). Cruza cada reporte y cada
  tarjeta en 9 periodos y 11 fechas de corte, tiene cifras calculadas a mano y prueba los atajos de fechas en sus bordes
  (semana que cruza de mes y de año, quincena de febrero, año bisiesto, otro cierre fiscal, hora de Panamá contra UTC) y con
  dos empresas. Una prueba más en `tests/test_pantallas.py` vigila que la barra de atajos sea una sola y que las
  tarjetas digan su fecha.
* Contra el código **anterior**, 25 de esas 45 pruebas fallan (todo lo de los hallazgos H1 a H8 y los atajos nuevos); las
  que comparan cifras de estado de resultados, balance, flujo, ITBMS y antigüedad contra los apuntes pasan con el código
  anterior y con el nuevo, que es lo que confirma que las cuentas estaban bien.
* Para repetirlo: `scripts/test.sh dcasa_contabilidad`, o solo estas con
  `TEST_TAGS=/dcasa_contabilidad:TestAuditoriaPeriodo,/dcasa_contabilidad:TestAuditoriaSaldos,/dcasa_contabilidad:TestAuditoriaResumen scripts/test.sh dcasa_contabilidad`.
