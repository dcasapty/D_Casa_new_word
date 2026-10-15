# Consolidación de D'CASA (`dcasa_consolidacion`)

Junta los estados financieros de **varias empresas del grupo en uno solo**, sin contar dos veces lo que
las empresas se hacen entre ellas. Hoy D'CASA tiene una sola empresa, así que esto es para cuando haya
dos o más (multiempresa ya viene incluido en Odoo Community). Con una sola empresa funciona igual y te
avisa que el consolidado es esa misma empresa.

Todo sale de los **asientos publicados**. No se guarda ninguna cifra aparte: lo único que queda guardado
son las líneas que calculaste, y siempre puedes volver a calcularlas.

## Dónde está

**Facturación › Reportes contables › Consolidación.** Allí mismo, **Mapa de cuentas (consolidación)**
(solo para quien lleva la contabilidad).

## Cómo se usa

1. **Nuevo**. Ponle nombre (por ejemplo «Consolidado de septiembre»).
2. Elige el **reporte**: Estado de resultados, Balance general o Balance de comprobación.
3. Elige las **fechas**, o un **atajo de fechas** (Hoy · Esta semana · Esta quincena · Este mes · Mes pasado · Este
   trimestre · Este año fiscal: los mismos de la barra de los reportes, hora de Panamá; todos terminan hoy menos «Mes
   pasado»). El balance general es «al» último día, así que solo usa «Hasta». En la lista, la columna **Periodo** lo dice
   claro («Al 31/03/2030», «El 12/03/2030», «Del 01/03/2030 al 31/03/2030») y los filtros de arriba muestran las
   consolidaciones que **tocan** ese periodo.
4. Elige las **empresas del grupo**: solo las que tú tienes acceso, y todas deben usar la misma moneda.
   Si una empresa no te aparece en la lista, actívala antes en el selector de empresas (arriba a la
   derecha).
5. Pulsa **Calcular**. Quedan las líneas con una columna por empresa, una de **Eliminaciones** y una de
   **Consolidado**.
6. Lee el cuadro de **Advertencias** (si sale). Dice qué no cuadra entre las empresas y de cuánto es.
7. **Imprimir PDF** (una columna por empresa, eliminaciones y consolidado) o **Tabla dinámica** (filas =
   cuenta, columnas = empresa o eliminaciones; la columna «Total» de esa tabla es el consolidado).

Si después se publican o corrigen asientos, pulsa **Recalcular**: reemplaza las líneas, no las duplica.
Para cambiar las empresas, el reporte o las fechas, pulsa **Volver a borrador** (descarta las líneas) y
vuelve a calcular.

## Cómo se arma

- **Cada empresa** sale con las mismas reglas de los reportes contables de una empresa sola (ingresos,
  pasivos y patrimonio en positivo; lo de años anteriores pasa al patrimonio como «Resultados de
  ejercicios anteriores»). Si no hay eliminaciones, el consolidado es exactamente la suma de las
  empresas, y cada columna coincide con el reporte de esa empresa sola.
- **Las cuentas se unen por su código.** Las empresas de D'CASA usan el mismo plan (`l10n_pa`), así que
  la cuenta «121» de una se suma con la «121» de la otra. Una cuenta que solo existe en una empresa
  aparece igual.
- **Mapa de cuentas.** Solo hace falta si el plan de una empresa es distinto: dices a qué **código
  consolidado** va cada cuenta de cada empresa (y, si quieres, con qué nombre). Lo que esté en el mapa
  manda sobre el código.

## Cómo se leen las fechas (igual que en los reportes de una empresa)

| Reporte | Qué es | Fechas |
|---|---|---|
| Balance general | **Saldo** a un día | Solo «Hasta». Cada empresa pasa al patrimonio sus resultados de años anteriores y los del ejercicio en curso según **su propio** año fiscal |
| Estado de resultados | **Movimiento** de un periodo | De «Desde» a «Hasta», los dos días incluidos |
| Balance de comprobación | Las dos cosas | Saldo inicial = antes del «Desde»; debe y haber = del periodo; saldo final = al «Hasta» |

Los atajos del formulario se calculan igual que los de los reportes (`dcasa.reporte.contable._atajos`), así que «Este mes» es
lo mismo aquí que en el Estado de resultados de una empresa sola.

## Qué se elimina

Una operación es **entre empresas** cuando el tercero del apunte es la ficha de **otra** empresa del
grupo (la ficha de contacto de esa empresa) **o una persona de contacto de esa ficha** (un asiento manual puede llevar a la
persona que atiende y no a la empresa). Se eliminan solo estas:

| Reporte | Se elimina |
|---|---|
| Balance general | Cuentas **por cobrar** y **por pagar** con otra empresa del grupo |
| Estado de resultados | **Ingresos** y **gastos** con otra empresa del grupo |
| Balance de comprobación | Las dos cosas de arriba (saldo inicial, debe, haber y saldo final) |

Lo eliminado se ve en la columna **Eliminaciones**, así que siempre puedes comprobar la cuenta:
empresas + eliminaciones = consolidado. Para que esto funcione, las facturas y asientos entre empresas
deben llevar como tercero la ficha de la otra empresa.

**El ITBMS de una factura entre empresas no se elimina ni se avisa.** Las líneas de impuesto llevan el tercero de la factura,
pero lo que representan no es una deuda con la otra empresa sino con la DGI: A cobra 7 % a B y B lo acredita en su declaración.
Las dos cuentas de ITBMS se quedan como están (si son la misma cuenta, se compensan en su fila).

## Si algo no cuadra, te lo dice

El sistema **nunca esconde ni arregla solo** una diferencia entre empresas. Cada lado se elimina por su
propio importe y sale una advertencia:

- «**Descuadre entre A y B de $X**» cuando lo que A dice que B le debe no es lo que B dice que le debe a
  A, o cuando los ingresos de A con B no son los gastos de B con A. El balance consolidado mostrará la
  misma diferencia y dirá que **no cuadra** hasta que se corrijan los asientos.
- Si hay un **saldo con otra empresa en una cuenta que no es por cobrar ni por pagar** (un préstamo, un
  anticipo, un traspaso), no se elimina, pero se avisa.
- Si hay **dinero en tránsito entre empresas** (A registró el cobro de B y B registró el pago a A, pero ninguna lo ha cruzado con
  su banco), cada lado queda en «Recibos pendientes» / «Pagos pendientes»: se avisa como saldo con otra empresa en una cuenta que
  no es por cobrar ni por pagar. Se resuelve cruzando el cobro y el pago en la Conciliación de cada empresa.
- Si una **misma cuenta consolidada cae en secciones distintas** según la empresa (por ejemplo, activo
  corriente en una y no corriente en otra), cada parte queda en su sección y se avisa para revisar el mapa.

## Cuentas que solo tiene una empresa (nota azul, no es un error)

Una cuenta **nunca se pierde**: si no está en el mapa se une por su código y, si solo existe en una empresa, aparece sola en
su fila. Pero si en realidad es la misma cuenta que otra de otra empresa con otro código, el consolidado la muestra en dos
filas. Por eso, al calcular, el formulario (y el PDF) llevan una **nota azul** con las cuentas con saldo que ninguna otra
empresa del grupo tiene ni por código ni en el mapa. No es una advertencia: nada está mal. Si alguna es equivalente a otra,
únelas en el **Mapa de cuentas**; si no, se deja así. Una cuenta que ya está en el mapa (aunque sea para dejarla sola) no
vuelve a salir en la nota. El mapa muestra el **tipo de cuenta** de cada fila y se puede agrupar por él: así se ve que no se
junten, con el mismo código, una cuenta de ingresos y una de gastos.

## Qué NO hace (queda para el contador)

- **Monedas distintas.** Si las empresas no usan la misma moneda, el cálculo se detiene con un error claro («todavía no se
  consolidan monedas distintas») y el formulario lo avisa en rojo desde antes de calcular. No suma ni convierte nada ni inventa
  tipos de cambio: no hay conversión. Con la misma moneda (hoy todas usan el dólar), cada apunte entra por su importe en la
  moneda de la empresa.
- **Ajustes manuales de consolidación.** No crea asientos de consolidación ni toca la contabilidad de
  ninguna empresa. Cualquier ajuste se decide y se registra aparte.
- **Utilidades no realizadas en inventario** entre empresas (cuando una empresa le vende a otra mercadería
  que la otra todavía tiene en bodega). Si la otra empresa lo anotó como inventario y no como gasto, saldrá
  un descuadre de ingresos contra gastos: es justo la señal para que el contador lo trate.
- **Participaciones minoritarias**, eliminación de la inversión contra el capital de las subsidiarias y
  método de participación.
- **Préstamos y anticipos entre empresas**: solo se avisan, no se eliminan.
- **Conversión de año fiscal.** Cada empresa pasa sus resultados al patrimonio con **su propio** año
  fiscal; si no coinciden, el contador debe revisar cómo presentarlo.

## Qué debe validar el contador

1. Que las cuentas se unan bien: revisa el consolidado cuenta por cuenta la primera vez, y arma el
   **mapa de cuentas** si algún plan es distinto.
2. Que las operaciones entre empresas lleven la ficha de la otra empresa como tercero (si no, no se
   eliminan).
3. Que toda **advertencia** esté entendida y resuelta (o documentada) antes de usar las cifras.
4. Que el balance consolidado **cuadre** (activo = pasivo + patrimonio) y el de comprobación también
   (debe = haber).
5. El tratamiento de lo que queda fuera (lista de arriba): inventario entre empresas, préstamos entre
   empresas, minoritarios, monedas.
6. Que la primera vez coincida con los estados de cada empresa por separado.

## Quién puede qué

| Quién | Qué puede |
|---|---|
| Vendedoras y facturación | Nada: no ven la consolidación |
| Contabilidad (solo lectura) | Ver y imprimir lo ya calculado |
| Contador | Crear, **calcular**, recalcular, volver a borrador, imprimir y armar el mapa |

Solo se pueden incluir empresas a las que la persona tiene acceso; una consolidación con una empresa
a la que no tienes acceso ni la ves ni la puedes calcular. El estado, las advertencias y las líneas solo
los pone el botón **Calcular** (no se editan a mano).

## Para quien mantiene el módulo

- `dcasa.consolidacion` (cabecera, estado, advertencias) y `dcasa.consolidacion.linea` (cuenta, sección,
  columna, importe; solo lectura), `dcasa.consolidacion.mapa` (mapa de cuentas).
- `dcasa.consolidacion.motor` (abstracto, todo privado): lee los apuntes con los permisos de la persona
  (nunca con `sudo`), arma las celdas por empresa, elimina y genera las advertencias. Las líneas se
  escriben con `sudo` después de comprobar el grupo contable en el servidor.
- El reporte PDF es `dcasa_consolidacion.reporte_consolidacion` (hoja carta horizontal).
- Se apoya en las constantes de `dcasa_contabilidad/models/reportes.py` (secciones, signos, tipos de
  resultados). No toca `dcasa_contabilidad`.

### Pruebas

Auditoría (`tests/test_auditoria_consolidacion.py`, con el cálculo independiente en SQL de `tests/oraculo_consolidacion.py`):
dos empresas con facturas reales entre ellas (con y sin ITBMS, en las dos direcciones, con nota de crédito, de un año anterior,
fuera del periodo, en borrador, con un contacto de la otra empresa y con cobros que esperan su movimiento). Cada sección del
estado de resultados y del balance, y el debe y haber de la comprobación, se cruzan contra los apuntes en 7 periodos y 9
cortes; hay cifras a mano, fechas borde, años fiscales distintos, las notas del mapa y los atajos de fechas.

`scripts/test.sh dcasa_base,dcasa_invoice,dcasa_interfaz,dcasa_contabilidad,dcasa_consolidacion`
(o solo `dcasa_consolidacion` con sus dependencias ya instaladas). Cubren, entre otras cosas: que el
consolidado sea la suma de las empresas y que cada empresa coincida con `dcasa.reporte.contable`; la
eliminación de por cobrar/por pagar y de ingresos/gastos; los descuadres; el mapa por código y manual;
monedas distintas; permisos y empresas no permitidas; que el balance cuadre; el PDF; y que recalcular no
duplique líneas. La superficie RPC está anotada en `addons/dcasa_base/tests/test_superficie_rpc.py`.
