# Nómina de D'CASA (`dcasa_nomina`)

Planilla quincenal, décimo tercer mes, vacaciones, prima de antigüedad, liquidación y reembolsos en nómina,
sobre los empleados de Odoo (`hr`). Menú **Nómina** (lo ven Gerencia y quien tenga el rol «Administra la
nómina»; cualquier persona del equipo ve **Mis gastos por reembolsar**, un menú aparte, con su propio ícono de recibo,
que no es de Nómina).

## La regla de oro: las tasas las valida el contador

La ley cambia (la cuota patronal del seguro social sube por pasos hasta 2029) y D'CASA no es quien la interpreta.
Por eso **ninguna tasa vive en el código**: están en **Nómina › Configuración › Tasas y reglas**, cada juego con su
fecha de vigencia.

* Las cifras que vienen de fábrica salieron de fuentes públicas (despachos de abogados y medios sobre la Ley 462 de
  2025 y el Código Fiscal), **no de la Gaceta Oficial**, y quedan **«Por validar»**.
* Con tasas por validar la planilla se puede **calcular como borrador** para ver cómo queda, pero **no se puede
  confirmar** (no genera asiento) hasta que el contador las valide con el botón **Validar (contador)**.
* **Faltan a propósito** y no se rellenan a ojo: el **riesgo profesional** (depende de la clase de riesgo que le
  asigna la CSS a D'CASA) y los aportes del **décimo tercer mes** (las fuentes no coinciden). Sin ellos no se valida.
* Una vigencia validada **no se edita**: para cambiarla se reabre; si ya la usó una planilla confirmada, se crea otra
  vigencia con «Duplicar» y la fecha desde la que cambia.

### Lo que el contador tiene que confirmar (checklist)

1. Seguro social: 9,75 % trabajador y 13,25 % patrono desde abril de 2025; los aumentos de marzo de 2027 (14,25 %) y
   marzo de 2029 (15,25 %) vienen cargados como vigencias futuras por validar. **Confirmar fechas y porcentajes.**
2. Seguro educativo: 1,25 % trabajador, 1,50 % patrono.
3. **Riesgo profesional** del patrono (la clase de riesgo de D'CASA).
4. **ISR**: tramos (0 % hasta B/. 11,000; 15 % hasta B/. 50,000; 25 % el excedente) y el método de retención por
   proyección anual (ver más abajo). ¿La renta se calcula después de restar seguro social y educativo?
   (casilla en la pestaña «Planilla quincenal»). Deducciones por persona (dependientes, intereses…) en su ficha.
5. **Décimo tercer mes**: aportes del trabajador y del patrono (la quincena y el décimo pueden diferir; no se
   presumen). El décimo no retiene ISR en este sistema: confirmarlo.
6. **Cuentas**: Nómina › Configuración › Cuentas y diario. Se proponen del plan de Panamá (514 gastos en salarios,
   515 cargas sociales, 241 sueldos por pagar, 242 cargas sociales por pagar, 232 ISR por pagar, 243 provisión del
   décimo): las confirma el contador.
7. **Provisión del décimo**: marcar o no «Provisionar el décimo tercer mes en cada planilla».
8. **Vacaciones y prima**: un día de descanso por cada 11 días trabajados (30 días por 11 meses); prima de 1 semana
   de salario por año (semana = salario mensual / 4,3333). Confirmar si el promedio de 11 meses debe incluir
   comisiones y horas extras, y si la prima se paga en toda terminación.
9. Base del **CSS**: topes o excepciones que apliquen.

## Cómo se usa

1. **Fichas** (Nómina › Colaboradores, o la app Empleados): salario mensual (con historial: un cambio de salario se
   anota como nueva versión con su fecha), fecha de ingreso (pestaña Payroll › Contract), cédula, seguro social,
   cuenta bancaria. En la sección «Nómina D'CASA» de esa pestaña: incluir en planilla, forma de pago y deducciones de
   ISR del año. Quien no tiene fecha de ingreso o salario sale en los **avisos** de la planilla.
2. **Planilla quincenal**: Nómina › Planillas quincenales › Nuevo (propone la última quincena completa). **Calcular**
   arma una línea por colaborador: salario de la quincena (medio salario mensual; quien entró o salió a mitad cobra
   solo sus días), seguro social, seguro educativo, ISR y neto. En cada línea se escriben a mano **otros ingresos**
   (horas extras, bonos: pagan aportes e ISR) y **otros descuentos** (préstamos, adelantos). **Calcular** otra vez
   conserva lo escrito a mano.
3. **Confirmar y contabilizar** publica el asiento (exige tasas validadas y las cuentas configuradas):
   * Débito: sueldos (devengado), cargas sociales (aportes del patrono), gastos de reembolsos.
   * Crédito: sueldos por pagar (neto de cada persona, a nombre de su contacto), seguro social (trabajador +
     patrono), seguro educativo, riesgo profesional, ISR retenido y otros descuentos.
4. **Pagar**: elige el banco o la caja en «Pagar desde»; se crea un pago por colaborador, que se concilia con el
   extracto como cualquier pago (Facturación › Bancos › Conciliación).
5. **Comprobante de pago** (PDF por colaborador) desde la línea o desde Acción › Imprimir; **Resumen de la planilla**
   (PDF) desde la planilla.
6. **Cancelar**: borrador o calculada se cancela; una confirmada se reversa (asiento de reverso) y sus reembolsos
   quedan libres; con pagos hechos, primero se anulan los pagos.
7. No se paga dos veces el mismo periodo (el sistema lo impide).

### ISR (retención por proyección anual)

Para cada quincena se proyecta el salario completo a 24 quincenas, se le restan las deducciones de la persona (y, si
los parámetros lo dicen, el seguro social y educativo), se aplican los tramos y el impuesto anual se divide entre 24
(proporcional a los días trabajados). **Lo extra** de esa quincena (horas extras, bonos) no se proyecta: paga solo
el impuesto adicional que causa. **Es un método de retención razonable pero el contador debe validarlo.**

## Décimo tercer mes

Nómina › Décimo tercer mes › Nuevo: año y partida (1.ª: 1 de diciembre a 31 de marzo, se paga el 15 de abril; 2.ª:
abril a julio, 15 de agosto; 3.ª: agosto a noviembre, 15 de diciembre). Cada partida = **lo devengado en sus 4
meses / 12**, sacado de las planillas quincenales confirmadas. Si el sistema solo tiene planillas de una parte del
periodo (por ejemplo la primera partida después de empezar a usar el sistema), **el resto se estima con el salario
de cada día (salario mensual / 30) y se avisa**; la base se puede corregir a mano en la línea. Los aportes salen de
las tasas del décimo (confirmadas por el contador). Mismo flujo: calcular, confirmar, pagar.

Con «Provisionar el décimo» marcado, cada planilla quincenal también registra 1/12 de lo devengado contra la
cuenta de provisión (243) y la partida se paga contra esa cuenta; sin marcar, el gasto se reconoce al pagar la partida.

## Vacaciones, prima y liquidación

* **Saldo de vacaciones** (en la ficha, pestaña Payroll): ganadas = días de servicio / 11; tomadas = las confirmadas
  en **Nómina › Vacaciones**; saldo y su valor (días × promedio mensual / 30). Mientras descansa, la planilla sigue
  pagando su salario normal; el saldo sin tomar se paga en la liquidación.
* **Prima de antigüedad acumulada** (en la ficha): una semana de salario por año de servicio (con fracción).
* **Liquidaciones** (Nómina › Liquidaciones): hoja de cálculo para el contador con salario sin pagar (desde el día
  siguiente a la última planilla confirmada), décimo proporcional, vacaciones sin tomar, prima y descuentos de
  seguro social y educativo. **La indemnización o el preaviso y el ISR de la liquidación los escribe el contador**
  (dependen del motivo de la salida). No genera asiento ni pago: lo que se pague se registra en una planilla.

## Reembolsos en nómina

Gastos que paga un colaborador de su bolsillo. **Mis gastos por reembolsar** (antes «Mis reembolsos»; cualquier persona
del equipo, es su propio menú y no cuelga de Nómina ni de Facturación): si pagaste algo de tu bolsillo para la empresa
(un taxi, bolsas, una reparación), registra el concepto, el monto y la **foto del recibo** y lo envía. Quien administra
la nómina lo ve en **Nómina › Reembolsos** y lo **aprueba** (elige la cuenta de gasto) o lo **rechaza con un motivo**. La
siguiente planilla quincenal lo suma al neto de esa persona, **sin pagar seguro social, educativo ni ISR**, y al
confirmarla queda contabilizado (gasto contra sueldos por pagar). Nadie aprueba su propio reembolso ni ve los de otros;
un reembolso enviado ya no se edita.

Se dejó como menú propio, y no dentro de Nómina o Facturación, porque lo usa todo el equipo y quien solo vende no debe
abrir la app de Nómina ni necesita permiso de facturar. Tiene un ícono distinto al de Nómina (un recibo) para que no
parezca que la vendedora tiene la Nómina habilitada. Para registrar gastos hace falta que el usuario esté ligado a su
ficha de colaborador.

## Bono por meta de ventas

Decisión del jefe (2026-10-16). Vive en `models/meta_ventas.py`; las cifras, en **Nómina › Configuración › Meta de
ventas** (con vigencia por mes).

* **Quién participa:** quien está en un departamento marcado **«Participa en la meta de ventas»** (Empleados ›
  Departamentos; al instalar se marca solo el que se llama «Ventas») y tiene su **usuario relacionado** en la ficha.
  Las ventas son las facturas donde esa persona es el «Vendedor».
* **Qué cuenta:** solo las facturas **cobradas completas** (caja recibió todo, también en los apartados), **sin
  ITBMS**, en el **mes en que se completó el pago** (la última conciliación de la factura). Las notas de crédito de
  esas ventas restan: la que revierte la factura y también la que se aplicó a ella aunque se haya hecho suelta (en su
  mes, o en el mes en que se completó el pago si llegaron antes). La devolución de una venta que nunca contó (pagada
  antes de que rigiera la primera meta) no resta. Las facturas cargadas del sistema viejo no cuentan.
* **Una sola vez:** cada factura y cada nota cuenta en un solo bono. Si su mes ya entró en una planilla (aunque haya
  dado cero), cuenta en el primer mes abierto después: un pago que se registra tarde con fecha atrasada no se pierde.
  Lo que ya está en un bono cerrado no vuelve a contar: un pago anulado y registrado de nuevo otro mes no paga dos
  veces. Lo ya pagado no se descuenta después (si una venta pagada se queda sin cobrar, lo decide Gerencia).
* **El bono:** si lo cobrado del mes **llega a la meta** (30,000 desde octubre de 2026), es el **1 % de todo** lo
  cobrado (60,000 → 600). Si no llega, no hay bono. El ritmo diario (1,000) es solo una guía que ve la vendedora.
* **El pago:** entra solo en la **primera planilla quincenal del mes siguiente** (del 1 al 15), en la columna «Bono
  por meta» de la línea: suma a lo devengado y paga seguro social, seguro educativo e ISR como lo extra (REQUIERE
  CONTADOR: confirmar que la comisión se trata así y si entra en el promedio de vacaciones y la prima). Esa planilla
  enlaza el bono del mes anterior y cualquiera que haya quedado por pagar de antes, aunque la persona ya no esté en
  Ventas. Quien ganó bono y no entra en la planilla (sin salario o fecha de ingreso) sale en los avisos y su bono queda
  **por pagar** hasta la próxima primera quincena que la incluya. El bono sale en el comprobante de pago. Una planilla
  confirmada lo deja **pagado**; si se reversa, vuelve a quedar por pagar (la planilla cancelada no cambia sus
  montos). Un bono que ya está en una planilla no se recalcula solo: se pone al día al volver a calcular la planilla.
* **Lo que ve cada vendedora:** en su Inicio, «Tu meta del mes»: **solo** el porcentaje que lleva, en grande junto a
  la barra (la barra se llena hasta el 100 %; el número puede pasar), unas palabras de ánimo según lo que lleva y el
  botón **«Ver mis ventas»**, que abre las ventas que suman a su porcentaje del mes (facturas cobradas completas y las
  notas de crédito que restan).
  Decisión de la dueña (2026-10-16): **ninguna cifra de dinero** (ni la meta, ni el porcentaje del bono, ni lo
  cobrado, ni lo que falta, ni el ritmo del día); el servidor tampoco las manda al navegador. Solo lo suyo; nunca lo
  de la tienda ni lo de otra persona. Las cifras las ve Gerencia en Nómina › Bono por meta.
* **Lo que ve Gerencia:** **Nómina › Bono por meta** (cada persona, mes a mes, con las facturas que cuentan y las
  notas que restan). Al abrirlo se pone al día el mes en curso y el anterior; también se pone al día solo cada día.
* **Cambiar las cifras:** se crea una meta nueva que rija desde un mes. Un mes con bonos ya en una planilla no cambia.
  Una meta que todavía no pagó bonos se puede borrar: sus bonos por pagar se vuelven a calcular con la que quede.

## Seguridad

Los sueldos son datos delicados: solo los ve el rol **Administra la nómina**, que **Gerencia incluye**. La vendedora no
ve planillas, sueldos ni tasas. El estado de una planilla, de una tasa o de un reembolso solo cambia con sus botones
(el servidor lo exige, no solo la pantalla). Una planilla confirmada no se edita ni se borra.

## Lo que NO hace (REQUIERE CONTADOR o queda para después)

* Cálculo de **horas extras** por recargo (25 %, 50 %, 75 %): se escribe el monto en «otros ingresos».
* **Indemnización y preaviso** por despido; **ISR de la liquidación**; **fondo de cesantía**.
* Archivos de **pago masivo del banco (ACH)**: cada banco tiene su formato y no hay muestra; hoy se pagan con los
  pagos de Odoo.
* **Declaraciones** a la CSS y a la DGI (planillas electrónicas): requieren el formato oficial.
* Cambio de moneda: la planilla es en dólares (USD).

## Pruebas

`scripts/test.sh dcasa_nomina`: la aritmética (redondeo, ISR, prorrateo, décimo, vacaciones, prima), el cálculo de la
quincena con cifras de prueba, el asiento que cuadra (con y sin provisión), tasas sin validar que impiden confirmar,
periodos que no se pagan dos veces, pago y reverso, reembolsos de punta a punta, liquidación y los permisos (la
vendedora no ve nada, nadie aprueba lo suyo, los estados no se escriben por RPC).
