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

---

# Presupuestos, consolidación, cierre y conciliación

Segunda revisión (15 de octubre de 2026), con el mismo método de arriba: cada cifra de la pantalla se compara con un cálculo
hecho aparte, directo en SQL sobre los apuntes publicados, y los errores se prueban con datos de una mueblería. Los números
de los ejemplos son **datos de prueba**, no de la empresa. La dueña pidió que presupuestos, consolidación y mapa de cuentas
estén «muy bien hechos a nivel de filtros, lógica, aritmética y contabilidad».

## En pocas palabras (segunda revisión)

* **Las cuentas estaban bien.** «Lo real» de un presupuesto coincide con los apuntes en 9 periodos (un día, la semana, el mes,
  el mes pasado, el año a hoy, el año, un cruce de año, el año anterior y mitad de mes) para 9 tipos de línea (ingreso, gasto,
  los dos canales de venta, banco, préstamo, capital y mobiliario). La consolidación suma las empresas y resta lo eliminado, sección
  por sección, en 7 periodos y 9 fechas de corte, y el balance consolidado cuadra en todas.
* **Lo que fallaba era lo que la pantalla decía y lo que dejaba pasar.** Se encontraron **14 cosas** (11 de lógica o de lo que la pantalla decía, 3 que faltaban) y las 14 están
  arregladas (abajo). Los más serios: el cierre de mes y la guía de Brian decían «Todo conciliado» con un cobro en efectivo sin cruzar; un
  presupuesto mezclaba ventas con gastos en un solo «total»; y una factura normal entre dos empresas del grupo llenaba el
  consolidado de advertencias falsas de ITBMS.
* **Quedan 12 preguntas para la contadora** (al final). Ninguna se decidió sin ella.

## Hallazgos y lo que se corrigió

**Q1. El cierre de mes decía «Todo conciliado» con un cobro sin cruzar (igual que la tarjeta H1 de arriba).**
*Qué estaba mal:* el paso «Bancos, Yappy, tarjeta y caja conciliados» del Cierre de mes y la guía `guia_cierre_mes` de Brian solo
contaban movimientos del extracto. Un cobro registrado con «Registrar pago» espera en «Recibos pendientes» y no suma al dinero
de la caja hasta que se cruza con su movimiento. *Ejemplo:* abono de $200 en efectivo en una factura, sin movimiento de caja; el
extracto del banco al día. El paso decía «Todo conciliado» y la gerencia podía cerrar septiembre con $200 que el cajón tiene y
la contabilidad no. *Cómo quedó:* el paso (y la guía de Brian) salen de la **misma cuenta** que la tarjeta del Resumen
(`_saldos_bancos`) y dicen, por diario, cuántos movimientos faltan y cuántos cobros o pagos faltan por cruzar y de cuánto:
«Efectivo: 1 cobro sin cruzar ($200.00)». Impide cerrar, igual que un movimiento sin conciliar. «Ver» abre la pantalla de
Conciliación.

**Q2. El cierre de una empresa podía leer los reportes de todas las empresas activas.**
*Qué estaba mal:* el cierre de la empresa A calculaba «el balance cuadra» y «el ITBMS del mes» con las empresas que estuvieran
activas en pantalla, no con la que se cierra. *Cómo quedó:* todos los pasos usan solo la empresa del cierre. (Hoy hay una sola
empresa: esto evita un error el día que haya dos.)

**Q3. Un cobro registrado sin movimiento de caja no tenía dónde cruzarse.**
*Qué estaba mal:* la pantalla de Conciliación solo parte de los movimientos del extracto. Un cobro en efectivo no trae
movimiento: no aparecía en ninguna parte. *Cómo quedó:* si un banco o la caja tiene cobros o pagos esperando su movimiento, la
lista lleva una segunda pestaña, **«Cobros y pagos sin movimiento»**, con el botón **«Crear el movimiento y cruzar»** (registra
la entrada o la salida en la caja o el banco y la cruza con el cobro; se puede deshacer como cualquier conciliación). En un banco
pide confirmar, porque si luego se importa el extracto, ese movimiento llegaría repetido. Si el mes del pago ya está cerrado, el
movimiento lleva el primer día abierto y la pantalla lo dice.

**P1. En un presupuesto, «% ejecutado» decía 0 % con planeado en cero.**
*Ejemplo:* planeado $0 para ventas y real $1,800 (ventas de octubre al 14). Mostraba 0 % y «Diferencia» −1,800, sin explicar.
*Cómo quedó:* no inventa el porcentaje; la línea dice **«Sin presupuesto»** (o «Sin movimiento» si tampoco hubo nada).

**P2. Un ingreso por encima de lo planeado salía en rojo.**
*Ejemplo:* meta de ventas $1,500 y real $1,800: «diferencia» −300 en rojo, como si fuera un problema. En un gasto, planeado $200
y real $280 (−80) sí es un problema. *Cómo quedó:* el color sale del tipo de línea: gasto contra tope («Dentro» / «Te pasaste») e
ingreso contra meta («En camino» / «Meta cumplida»). La columna se llama **«Por ejecutar»** (planeado − real) y su ayuda
explica el signo.

**P3. Los totales sumaban ventas con gastos.**
*Ejemplo:* ventas planeadas $2,000 y gastos planeados $300 daban «Planeado $2,300», que no significa nada. *Cómo quedó:* tres
totales: **ingresos, gastos y resultado** (2,000 − 300 = 1,700 planeado; real igual). Las cuentas de balance (banco, préstamos)
no entran al resultado.

**P4. El detalle por canal se sumaba dos veces.**
*Ejemplo:* una línea de la cuenta de ventas ($2,000 planeado, $1,800 real) y otra de la misma cuenta solo para la tienda
física ($1,000 planeado, $870 real): el total sumaba $3,000 y $2,670. *Cómo quedó:* la línea por canal es un **detalle** de la
general y no se suma otra vez (total $2,000 / $1,800; el presupuesto avisa). La misma cuenta con la misma analítica dos
veces ya no se permite (mostraría el mismo real dos veces).

**P5. Faltaban filtros de fecha y una forma de comparar contra el tiempo.**
*Cómo quedó:* en la lista de presupuestos hay filtros de estado y los siete atajos (Hoy · Esta semana · Esta quincena · Este mes
· Mes pasado · Este trimestre · Este año fiscal) que muestran los presupuestos cuyo periodo **toca** esos días. Y un campo
**«Tiempo transcurrido»** (45 % el 14 de octubre en un presupuesto de octubre) para comparar con el % ejecutado: gastar 80 % con
30 % del tiempo es ir muy rápido.

**P6. El botón «Movimientos» del presupuesto no filtraba por empresa.** Ahora sí.

**K1. Una factura normal entre dos empresas del grupo llenaba el consolidado de advertencias falsas de ITBMS.**
*Ejemplo:* A le factura $1,000 + $70 de ITBMS a B. El consolidado decía «A tiene un saldo acreedor de $70 con B en la cuenta ITBMS
a pagar, que no es por cobrar ni por pagar» (y lo mismo de B). Salía con **cada** factura: la gente aprende a ignorar las
advertencias. *Cómo quedó:* las líneas de impuesto no se miran como deuda entre empresas (el ITBMS se debe a la DGI, no a la otra
empresa). Se siguen eliminando por cobrar/por pagar ($1,070 de cada lado) e ingresos/gastos ($1,000).

**K2. Un asiento a nombre de una persona de la otra empresa no se eliminaba.**
*Ejemplo:* A registra a mano una venta de $60 a «Contacto de la zona libre» (una persona de la ficha de B). Como el tercero no
era la ficha, los $60 de ventas (y los $60 de gastos de B) quedaban dentro del consolidado: ventas y gastos $60 más altos.
*Cómo quedó:* se reconoce como la otra empresa a su ficha **y a sus contactos**.

**K3. Las cuentas que solo tiene una empresa no se perdían, pero nadie lo veía.**
*Cómo quedó:* una cuenta nunca se pierde (se une por código y, si es única, sale sola). Ahora el formulario y el PDF llevan una
**nota azul** (no una advertencia) con las cuentas con saldo que ninguna otra empresa tiene ni por código ni en el mapa, para ver
si falta unirlas. El **Mapa de cuentas** muestra y agrupa por **tipo de cuenta**, para ver que no se junten un ingreso y un
gasto.

**K4. La lista de consolidaciones mostraba un «Desde» que el balance no usa.** *Cómo quedó:* una columna **Periodo** («Al
31/03/2030», «El 12/03/2030», «Del 01/03/2030 al 31/03/2030»), igual que en el PDF y que en los reportes.

**K5. Faltaban los atajos de fecha en la consolidación.** El formulario tiene el selector de atajos (llena el «Desde» y el «Hasta»)
y la lista tiene los mismos siete filtros.

## Lo que se revisó y estaba bien (segunda revisión)

* **Presupuestos:** lo real (borradores y cancelados fuera, una nota de crédito resta, solo del periodo y de la empresa del
  presupuesto, signo natural de ingresos, gastos, pasivos y patrimonio); la parte de cada apunte que va a un canal (60/40 en una
  venta repartida) contra las líneas analíticas de Odoo, que es otro camino. *Ejemplos:* ventas de septiembre = $600 − $100 de nota
  de crédito = $500; compras de septiembre = $500 − $50 = $450; canal tienda física en octubre al 14 = 60 % de $950 + $300 = $870.
* **Consolidación:** estado de resultados = suma de las empresas − eliminaciones, sección por sección; balance consolidado
  cuadra (activo = pasivo + patrimonio) y cada empresa por separado también; comprobación con debe = haber, saldos iniciales y
  finales que suman cero; eliminaciones de por cobrar/por pagar con facturas, notas de crédito, cobros parciales y un año
  anterior; lo de después del periodo, el borrador y las fechas borde (el mismo día entra; el día de antes y el de después, no);
  cada empresa con su propio año fiscal; los descuadres se avisan con su monto. *Ejemplo (balance al 31 de marzo de 2030):* por
  cobrar entre empresas $1,737 (A a B) + $321 (B a A) = $2,058, y lo mismo en por pagar.
* **Monedas:** si las empresas no usan la misma moneda, el cálculo se detiene con un mensaje claro y el formulario lo avisa; **no
  convierte ni inventa tipos de cambio**. Con la misma moneda (hoy todas en dólares) cada apunte entra por su importe.
* **Fechas coherentes con los reportes:** el balance consolidado usa solo el «Hasta» (es un saldo), el estado de resultados usa
  «Desde» y «Hasta» (movimiento) y los atajos son los mismos de la barra de los reportes.

## Para la contadora (segunda revisión)

* **C10. ITBMS entre empresas del grupo.** Hoy no se elimina (cada empresa lo debe o lo acredita a la DGI). ¿Es lo correcto para el
  consolidado, o quiere netearlo?
* **C11. Dinero en tránsito entre empresas.** Si A registró el cobro de B y B registró el pago a A y ninguna lo ha cruzado con su
  banco, quedan «Recibos pendientes» y «Pagos pendientes» de cada lado (se avisa, no se elimina). ¿Se elimina como lo que se
  deben entre ellas?
* **C12. Préstamos y anticipos entre empresas.** Solo se avisan. ¿En qué cuentas se llevarán y cómo se eliminan?
* **C13. Inventario o activos comprados entre empresas.** Si la compradora lo registra como inventario y no como gasto, sale un
  descuadre de ingresos contra gastos (la utilidad no realizada). ¿Cómo se trata?
* **C14. Monedas distintas.** Si algún día una empresa lleva otra moneda: ¿qué tipo de cambio (cierre, promedio) y de dónde sale?
  Hoy no se convierte.
* **C15. Años fiscales distintos entre empresas.** Cada empresa pasa sus resultados al patrimonio con su propio año fiscal. ¿Es lo
  que quiere el consolidado?
* **C16. Mapa de cuentas.** Cuando una empresa tenga un plan distinto: ¿qué cuenta de una equivale a cuál de la otra? La nota azul de
  cada cálculo lista las candidatas.
* **C17. Cuentas de balance en un presupuesto** (préstamos, compra de activos): hoy se miden contra un tope pero no entran al
  resultado. ¿Las quiere en el presupuesto o solo ingresos y gastos?
* **C18. Un presupuesto es de un solo periodo.** ¿Quiere uno por mes dentro del año (para ver el avance mes a mes) o le basta con
  «Tiempo transcurrido»?
* **C19. Cheques y cobros en tránsito en el cierre.** Hoy un cobro registrado sin cruzar **impide cerrar** el mes (igual que un
  movimiento del banco sin conciliar). Un cheque depositado el último día que el banco acredita días después se vería así. ¿Prefiere
  que solo avise (no impida)?
* **C20. Efectivo.** Para cada cobro en efectivo, ¿quiere llevar un movimiento de caja (ahora se crea con un clic desde
  «Cobros y pagos sin movimiento») o prefiere el saldo directo?
* **C21. Pendiente de C5 de arriba:** ¿suma al «Dinero en bancos y caja» lo que está en tránsito?

## Límites conocidos (segunda revisión)

* Los atajos de las listas de Presupuestos y Consolidación terminan hoy (como en los reportes): un presupuesto que empieza
  mañana no sale en «Este mes». Para ver todos los que siguen abiertos, el filtro «Vigentes».
* «Lo real» de un presupuesto no se guarda: se calcula al abrir la pantalla (siempre al día).
* La pantalla de Conciliación solo lista los diarios de banco y caja. Un diario de tipo «tarjeta de crédito» de Odoo no aparece (en
  D'CASA «Tarjeta» es un banco).
* `movimientos_por_conciliar` de Brian ya suma, además de los movimientos del extracto, los cobros y pagos que esperan su movimiento
  (cuántos y de cuánto, con la misma regla que la tarjeta, el cierre y la pantalla de Conciliación). Brian solo los **muestra**: cruzarlos
  lo hace una persona en «Cobros y pagos sin movimiento».
* En el consolidado, las líneas de impuesto no se eliminan nunca; si algún día hay que eliminar algo de ahí, sería una regla nueva.

## Cómo se probó (segunda revisión)

* **50 pruebas nuevas:** `dcasa_contabilidad/tests/test_presupuesto.py` (16, con `tests/oraculo_presupuesto.py`, SQL aparte),
  `dcasa_contabilidad/tests/test_cierre_conciliacion.py` (12), `dcasa_consolidacion/tests/test_auditoria_consolidacion.py` (21, con
  `tests/oraculo_consolidacion.py`) y 1 de Brian (`dcasa_brian/tests/test_herramientas_contabilidad.py`). Cifras a mano, fechas borde,
  dos empresas, hora de Panamá contra UTC.
* **Resultado con el código nuevo:** `scripts/test.sh dcasa_contabilidad,dcasa_consolidacion,dcasa_brian,dcasa_base` sobre una base
  limpia: **0 fallas en 219 pruebas** (contabilidad 158, consolidación 78, Brian 27, superficie RPC 6).
* **Contra el código anterior** (el de antes de esta revisión), de las 50 pruebas nuevas **44 fallan**. Las 6 que pasan son las que
  comparan contra los apuntes lo real de los presupuestos (4), el presupuesto con dos empresas y las fechas borde de la
  consolidación: confirman que esas cuentas ya estaban bien. En la consolidación, el cálculo aparte encontró el error K2: ventas
  consolidadas de marzo $1,560.00 contra $1,500.00 reales, y un «Descuadre de $60.00» que no existía.
* Para repetirlo: `scripts/test.sh dcasa_contabilidad,dcasa_consolidacion`, y para Brian
  `TEST_TAGS=/dcasa_brian:TestHerramientasContabilidad scripts/test.sh dcasa_brian`.
* Capturas de pantalla a 1366×768 con un navegador real (Conciliación con la pestaña nueva y el aviso para el banco, cierre de mes
  con «Efectivo: 1 cobro sin cruzar ($200.00)», presupuesto con totales y situación, consolidación con la nota azul y el selector
  de atajos): el botón «Crear el movimiento y cruzar» se probó de punta a punta.

---

# Cuestionario para la gerencia y la contadora (15 de octubre de 2026)

A partir de la **auditoría integral del 14 de octubre** (hecha con Chrome, solo lectura) se armó un cuestionario de **73 preguntas**
en palabras sencillas para la gerencia y la contadora. Sus respuestas definen el **trabajo contable** que hará la extensión de
Claude dentro de Odoo (cargar saldos, validar compras, conciliar, registrar gastos, cerrar meses): no se programa nada nuevo y el
plan de implementación se escribe con esas respuestas. Está publicado como página privada (con cajas de respuesta y un botón
«Copiar respuestas» para devolverlas por el chat); este resumen deja constancia de qué se pregunta.

| Grupo | De qué trata |
|---|---|
| A · Reglas del negocio | qué cuenta como «vendido», en qué día, ventas a crédito, apartados, quién factura y cobra, devoluciones |
| B · El punto de partida | fecha de los saldos iniciales, enero a julio, balance inicial, equivalencia de cuentas, conformidad de la carga, libro oficial |
| C · Dinero | todas las cuentas reales, extractos y conteo de caja, cierre diario, depósitos, comisiones de tarjeta y Yappy, ACH en negativo |
| D · Clientes y cobranza | centavos, saldos a favor, política de cobranza, incobrables |
| E · Proveedores y compras | las 16 compras «por validar», recepciones heredadas, vencidos, importaciones, compras sin factura |
| F · Inventario y costos | de dónde salen los costos, método de costo, inventario en el balance, duplicados, mermas, consignación |
| G · Gastos y nómina | lista de gastos, desde cuándo se registran, planilla, tasas, comisiones, adelantos, reembolsos |
| H · Impuestos | ITBMS, exentos y retenciones, otros impuestos, factura electrónica de la DGI, reportes que se presentan |
| I · Cierres y control | cierre de mes (agosto y septiembre), año fiscal, roles, segundo factor, plan de cuentas, comprobantes |
| J · Socios y Vendedores | costo real de los premios y del punto, cómo se anota el costo del programa, dictamen para el canje |
| K · Qué quiere ver la gerencia | los cinco números del día, presupuesto, otras empresas o monedas, a quién se envían reportes |
| L · Cómo trabajará la extensión | qué hace sola y qué pide aprobación, quién aprueba, usuario propio, fechas, copia de seguridad, orden, límites, informe final |

Las preguntas «Primero» (14) son las que hacen falta para empezar: A1, B1 a B3, B6, C1, C2, E1, F1, G1, I1, L1, L2 y L6.
Lo que dice la auditoría y todavía **no** se ha hecho en el sistema (propuestas, a decidir con la dueña): gráfica semanal de
Inicio según la respuesta A1, «Sin extracto cargado» en lugar de «Todo conciliado», el monto de los borradores en el aviso,
«Vencido» en lugar de «Debido» y separar lo vencido de los saldos a favor, el aviso de no facturar dos veces en la recepción de
las compras heredadas y la explicación de «Secuencias irregulares».

