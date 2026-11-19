# Comisión por las ventas del sitio web — diseño (fase 1)

Escrito el 2026-11-19 para que **Gerencia general** lo decida y luego se construya. **Nada de esto está programado**:
este documento solo propone, y cada decisión que no es obvia queda como pregunta (sección 10). No trae ningún
porcentaje, monto ni regla laboral inventada: donde falta un dato, dice quién lo pone.

Las referencias a archivos y líneas del sistema están al final (Anexo A), para quien construya o revise. Quien solo
decide puede leer las secciones 1, 2, 3, 6, 7 y 10.

## 1. Resumen de una página

1. **Qué cuenta:** una factura de un pedido que **nació en la tienda en línea** y quedó **pagada por completo**. No
   importa con qué se pagó (pasarela, Yappy o transferencia a mano, o en la tienda) ni quién cobró: el origen lo
   decide el pedido; el dinero, el pago completo.
2. **Sobre qué monto:** lo que de verdad entró: sin ITBMS, sin el cargo de envío, con los descuentos ya aplicados y
   menos las devoluciones.
3. **El porcentaje** lo escribe Gerencia general en una pantalla. **Hoy está vacío y así se queda hasta que lo decida**:
   sin porcentaje el sistema mide las ventas del sitio pero no calcula nada pagable. Cada cambio es una versión nueva
   que rige solo hacia adelante; el historial no se edita.
4. **Quién recibe:** una lista de **personas** (fichas de empleado) con su reparto, que suma 100 %. No depende del
   departamento: quien cambie de área sigue igual hasta que Gerencia cambie la lista.
5. **El libro:** cada venta y cada devolución queda en un libro que **no se edita ni se borra** (se corrige con un
   asiento contrario y su motivo). De ahí sale el **«Estado de comisión del sitio web»** de cada mes: factura por
   factura, su base, el porcentaje, el monto y el enlace. Con Excel y PDF. Gerencia ve todo; cada persona que recibe
   ve el suyo, solo para leer.
6. **Nada se paga solo.** Al cerrar el mes el sistema arma una **propuesta**; Gerencia la revisa y la ajusta (con
   motivo); la **aprueba una persona de Gerencia que no recibe comisión**; y entonces pasa a la **planilla** (primera
   quincena del mes siguiente, igual que el bono por meta) o se anota como pagada fuera de planilla.
7. **Confianza:** quienes reciben también construyen y administran el sistema, así que el estado de cada mes se
   **sella con una huella** que llega a Gerencia general y a la contadora, quien recibe no aprueba su propia comisión
   y el origen de cada pedido queda con un testigo que no se puede cambiar después. Hay cosas que no se pueden
   evitar y aquí se dicen con franqueza (sección 7).
8. **Lo legal y contable** (si esto es salario, qué descuentos lleva, décimo, vacaciones, renta) **lo deciden la
   contadora y el abogado**. Hoy el sistema trata el bono por meta como salario; la comisión web podrá cambiar de
   tratamiento sin reprogramar.
9. **Se construye por partes:** primero **medir y mostrar** (sin pagar nada); después propuesta y aprobación; al final
   el enlace con la planilla, cuando haya dictamen.
10. **Lo que se necesita de Gerencia general:** contestar 8 preguntas cortas (sección 10).

## 2. Qué cuenta como «venta del sitio web»

### La definición exacta

Una **venta del sitio web** es una **factura de cliente publicada y pagada por completo** (pagada o «en proceso de
pago», como en el bono por meta y en «Completadas» del Inicio) cuyas **líneas de producto vienen de un pedido que
nació en la tienda en línea**, y que **no es una compra de una de las personas que reciben la comisión**.

- **«Nació en la tienda en línea»** hoy se sabe por el campo `website_id` del pedido; la etiqueta «Web» del origen sale
  de ahí (Anexo A, A6). Ese campo se puede cambiar después por código, así que la comisión guarda además un **testigo
  de origen** que se escribe una sola vez al crear el pedido (sección 7).
- **Se mira línea por línea**, no la factura entera: una factura que junta un pedido de la web con otro de la tienda
  solo comisiona las líneas del pedido web.
- **El medio de pago nunca decide.** Sirve cualquier pasarela futura (Tilopay, el Yappy oficial u otra) con solo que
  su pago quede aplicado a la factura: no hay que programar nada por pasarela.
- Un **pago de pasarela sin factura todavía** no suma dinero, pero sale en una lista aparte para que nada del sitio
  quede sin ver (y para que alguien facture).

### Los casos

«Sí» = cuenta. «Decide Gerencia» = queda como parámetro de las reglas: **mientras Gerencia no lo conteste, esa venta
aparece en el estado como «en duda» y no suma al monto**; así se ve cuánto dinero depende de cada decisión. Donde dice
«recomiendo», es mi recomendación, no una decisión tomada.

| Caso | ¿Cuenta? | Por qué |
|---|---|---|
| Pedido de la web pagado con pasarela (Tilopay, Yappy oficial, futuras) | **Sí** | Nació en la web y la pasarela es solo el medio. Cuenta cuando la factura queda pagada por completo. |
| Pedido de la web pagado con transferencia o Yappy a mano | **Sí** | Igual: lo registra Caja y cuenta cuando la factura queda completa. Hoy el sitio cobra así (A7). |
| «Pago en la tienda» (apartado por la web, se paga en el local) | **Decide Gerencia** (recomiendo **sí**) | El pedido nació en la web y la web trajo la compra, pero el cobro y la atención son del local. Opciones: sí; no; sí solo si paga dentro del plazo del apartado. |
| Abonos de un apartado | **Solo cuando termina de pagarse** | Mismo criterio del bono por meta (A1): los abonos a medias no suman; si el apartado vence y se anula, no cuenta nada. No se paga «por pedazos»: complica y hay que deshacerlo si se devuelve. |
| Pedido de la web que una vendedora edita o termina por WhatsApp | **Sí** (sigue siendo web) | El pedido es el mismo. El estado lo marca «atendido por vendedora» para medirlo. Ojo con la meta de la vendedora: ver P4. |
| Empezó con Andrés (chat de la tienda) y se cerró en tienda | **Sí si se cerró sobre ese mismo pedido**; **No** si la vendedora armó una cotización nueva aparte | Andrés trabaja sobre el carrito real de la tienda (A8). Lo que decide es el documento que se factura, no la conversación. |
| Empezó con Andrés y la cotización la armó Juan (WhatsApp) | **Decide Gerencia** (recomiendo **no**) | Juan crea cotizaciones con origen «Chatbot» (A6): es otro canal, que ya se mide aparte en el panel de Juan. Es un interruptor por si algún día Gerencia lo quiere. |
| Cotización de la web pagada en la tienda | Igual que «Pago en la tienda» | Mismo pedido, mismo origen. |
| Factura que junta pedidos de varios orígenes | **Solo las líneas del pedido web** | La etiqueta de la factura da prioridad al chatbot sobre la web (A6); la comisión no se fía de esa etiqueta. |
| Devolución o nota de crédito | **Resta** | En el mes en que se hace (asiento contrario con motivo). Cuenta también la nota que se aplicó suelta, sin enlazar a la factura (como en el bono por meta, A1). Parcial: resta lo devuelto. |
| Devolución de una venta cuyo mes ya se pagó | **Resta en el mes en que ocurre**; si el saldo queda negativo, **se arrastra** | Nunca se descuenta de una planilla sin que Gerencia lo decida. Distinto del bono por meta, que no descuenta lo ya pagado (A1); aquí se propone lo contrario porque el libro lo permite sin esfuerzo. |
| Pago revertido (contracargo) o factura que vuelve a borrador o se cancela | **Resta** | La revisión nocturna lo detecta (como hace el programa de vendedores, A3) y asienta el reverso. |
| Pedido cancelado | **No** | No hay factura pagada. Si ya había contado y se cancela la factura, se reversa. |
| Factura sin pagar o pagada en parte | **No** (todavía) | Sale en «Pendientes de cobro» como información, sin dinero. |
| Descuentos y premios de Socios | **Se cuenta lo que entró** | El premio es una línea negativa que baja la base (A9); el descuento ya viene en el precio. Recomendado: neto, igual que el programa de vendedores. |
| Precio de campaña (Black Friday, etc.) | **Sí, al precio cobrado** | No hay un precio aparte. Ojo: quienes reciben también arman las campañas (sección 7). |
| Cargo de envío | **Decide Gerencia** (recomiendo **no**) | Es un costo que se traspasa al cliente, no venta del sitio; además el envío que suma el chat puede irse al pagar. Socios hace lo mismo con su base (A9). Se identifica por la línea de entrega y el producto de flete. |
| ITBMS | **No entra en la base** | Criterio contable vigente: ventas sin ITBMS (LEEME_PRIMERO §1). La comisión que se paga tampoco lleva ITBMS. |
| Comisión de la pasarela | **Decide Gerencia** (recomiendo **no restarla**) | Hoy no se sabe por venta: la contadora la ve en el banco. El interruptor sirve para cuando cada pago la guarde. |
| Compra de una de las personas que reciben | **No** | Misma regla «compra propia» del programa de vendedores (A3). |
| Facturas cargadas del sistema anterior o anteriores a la primera versión | **No** | «Solo hacia adelante», igual que el bono por meta (A1). |
| Venta financiada (Tafi, Crediviva) | **Sí**, al quedar pagada la factura | La financiera es una forma de pago (A7). Cómo se cruza lo que deposita después es asunto de la contadora. |
| Pedido al que después le cambian el origen a mano | **No** | Cuenta el testigo escrito al crear el pedido; el cambio dispara una alerta (sección 7). |

**Decisiones que quedan como parámetro de Gerencia:** qué hacer con «Pago en la tienda»; si el chatbot cuenta; si el
envío cuenta; y si se resta la comisión de la pasarela. La pantalla de reglas **no deja guardar una versión sin
contestar las cuatro** (mi recomendación aparece como ayuda, pero no viene marcada de antemano). Antes de que exista
la primera versión el sistema ya mide, y separa lo seguro de lo «en duda». El resto de la tabla son criterios fijos de
medición, que solo cambian con una versión nueva del sistema y su revisión.

## 3. La base y el porcentaje

### Sobre qué monto

**La base de una venta** es la suma, sin ITBMS, de las líneas de producto de la factura que vienen del pedido web, con
los descuentos ya puestos (también el premio de Socios y el precio de campaña, porque son parte del precio cobrado),
**sin la línea de envío ni los fletes**, y **menos lo que se devuelva** con notas de crédito.

Por qué así: es **lo que de verdad entró** y lo que ya usan el bono por meta y el programa de vendedores (A1, A3); y
es el criterio contable vigente (ventas sin ITBMS, dinero con ITBMS). El envío se queda fuera porque se traspasa al
cliente y puede cambiar al pagar. Cada uno de esos puntos es un parámetro o un criterio visible en el estado, no una
decisión escondida.

**La comisión** de una venta es `base × porcentaje ÷ 100`, en centavos enteros (mitad hacia arriba, como la planilla).
Se reparte entre las personas de la lista según su porcentaje de reparto; los centavos que sobren van, de uno en
uno y siempre en el mismo orden, a las primeras personas de la lista, para que la suma de las partes sea exactamente
el total.

### Cuándo cuenta una venta

- **Cuando su factura queda pagada por completo** (el mismo momento en que hoy se dan los puntos de Socios y la
  comisión de vendedores: A3). Los abonos a medias no cuentan.
- **En el mes de Panamá en que se anota en el libro.** El libro solo agrega filas, así que lo que se anota en
  noviembre **queda en noviembre para siempre**: no hay meses que se reabren ni ventas que «llegan tarde». Un pago con
  fecha atrasada se anota el día que se registra y el estado dice «cobrado el 28/11, anotado el 02/12». (El bono por
  meta, en cambio, cuenta por el mes del último pago y tiene que reacomodar los meses cerrados: A1.)
- Una devolución o un reverso se anota en el mes en que ocurre, nunca dentro de un mes sellado.

### Cómo define Gerencia el porcentaje

Una sola pantalla, **Comisión del sitio web › Reglas**, con pocos campos en palabras sencillas:

| Campo | Cómo viene |
|---|---|
| Porcentaje | **Vacío.** Sin porcentaje no se calcula nada pagable (las ventas se miden igual). |
| Rige desde | Fecha y hora; **solo hacia adelante** (no se acepta una fecha pasada ni anterior a otra versión ya programada). |
| Quiénes reciben y su reparto | Lista de empleados, suma 100 % (sección 4). |
| Las cuatro decisiones de la sección 2 | **Sin responder.** No deja guardar hasta contestarlas. |
| Cómo se trata al pagar (salario / sin descuentos / fuera de planilla) | **Vacío** hasta el dictamen (sección 8). Sin él se puede medir y proponer, no aprobar un pago. |
| Cuándo se paga | La planilla en que se manda (sección 6). |
| Motivo | Texto libre: se ve en el historial. |

Cada guardado crea una **versión nueva**: la versión **no se edita ni se borra** (igual que las reglas del programa
de vendedores, A3) y un error se corrige con otra versión. Cada venta guarda con qué versión y qué porcentaje nació; lo
ya anotado **no se recalcula** nunca. Pausar el programa es guardar una versión con el porcentaje vacío.
Es un porcentaje fijo sobre toda la base; escalones, topes o metas quedan para el futuro (sección 11).

**Ninguna cifra inventada.** No hay porcentajes de ejemplo en el código ni en los datos que se instalan: el módulo
nace sin ninguna versión. Las pruebas usan cifras de prueba que ellas mismas crean, como hacen las del bono por
meta (A1).

## 4. Quiénes reciben

- La lista es parte de cada versión de las reglas: **empleados** (`hr.employee`) con su **porcentaje de reparto**, y
  una restricción exige que sumen 100 %. No usa el departamento: el bono por meta sí lo usa («Participa en la meta de
  ventas», A1) y por eso quien cambia de departamento deja de participar; aquí no pasa.
- Para **ver su estado** cada persona necesita su usuario ligado a la ficha de empleado. Para **cobrar por la
  planilla** necesita además estar incluida en planilla, con fecha de ingreso y salario (como cualquier colaborador:
  A2). Si falta algo, la propuesta lo avisa y esa parte queda por pagar para la próxima planilla que la incluya,
  igual que el bono por meta. Quien no esté en planilla (por ejemplo un socio o alguien por honorarios) se paga
  **fuera de planilla**: el sistema lo anota con su referencia, no mueve dinero.
- **Quien entra a mitad de mes:** recibe desde las ventas que se anoten con él en la lista. Gerencia guarda una versión
  nueva (rige desde ya; no se puede poner una fecha pasada).
- **Quien sale a mitad de mes:** deja de recibir desde la versión nueva. Lo que ya se anotó con él **sigue siendo
  suyo**, con el reparto de ese momento. Si Gerencia quiere algo distinto (por ejemplo, repartir lo de los últimos
  días), lo ajusta **en la propuesta, con motivo**, y queda a la vista. La propuesta marca en rojo a quien sale con
  saldo pendiente.
- **No se prorratea por días** como el sueldo de la planilla: la comisión nace de ventas, no del calendario; la
  comisión sigue a la venta y no al día.

## 5. El libro y el estado de cuenta transparente

### El libro

Igual que el libro del programa de vendedores (A3), con dinero en vez de puntos:

- **Una venta del sitio** (`dcasa.web.venta`): una fila por factura con la base, el porcentaje, la versión de las
  reglas, cómo se pagó (pasarela, a mano o en la tienda), si el pago está conciliado con el banco, si la atendió una
  vendedora, y las referencias al pedido, la factura y los pagos. Congela lo que se sabía el día que se anotó.
- **El libro** (`dcasa.web.movimiento`): una fila por persona y por hecho, en centavos. Tipos: **venta**, **devolución**,
  **reverso** (pago revertido, factura anulada), **ajuste** (solo Gerencia, siempre con motivo) y **liquidación** (lo
  que se manda a pagar al aprobar). El **saldo** de cada persona es **la suma de sus filas**: no existe una columna de
  saldo. Una fila **no se edita ni se borra**; una corrección es **otra fila con la cifra contraria, su motivo y su
  autor**. Una devolución se reparte con las mismas partes con que nació la venta, aunque la lista haya cambiado.

### El «Estado de comisión del sitio web»

Pantalla mensual (mes en curso o cerrado). Cada fila:

| Fecha de cobro | Anotada el | Factura (enlace) | Cómo pagó | ¿Conciliada con el banco? | ¿Atendió vendedora? | Base | % | Comisión | Mi parte |
|---|---|---|---|---|---|---|---|---|---|

Con **total del mes** (facturas, base, comisión), filtros (mes, persona, forma de pago, con o sin vendedora, con
devolución, sin conciliar), **Excel** y **PDF**. Debajo, tres bloques de información que no suman dinero:
**Pendientes de cobro** (facturas del sitio por pagar), **Pagos del sitio sin factura todavía**, y **Alertas**
(facturas del sitio pagadas que el sistema no pudo anotar, pedidos cuyo origen cambió después de contar, ventas sin
conciliar). Un mes cerrado lleva su **huella** (sección 7).

**Cómo se ve una venta que se revierte** (con letras, sin cifras): la venta A suma `+B×P` en el mes que se anota; si
después se devuelve, en el mes de la devolución aparece otra fila `−B×P` («Devolución, nota de crédito …») y el total de
ese mes baja. El mes de la venta **no cambia**.

**Quién lo ve**

| Quién | Qué ve |
|---|---|
| Gerencia (y quien aprueba) | Todo, con enlace a cada factura y pedido. |
| Cada persona que recibe | El estado completo de ventas, totales y el porcentaje que rige, y **su** parte y saldo; no la parte de otra persona. **No ve el nombre del cliente** ni abre facturas si no tiene ya permiso de ventas (datos de personas). Solo lectura. |
| Vendedoras, Caja, Marketing y todos los demás | Nada: ni el menú ni por enlace. |

## 6. Cómo se paga

### Las tres piezas que pidió Gerencia, y mi recomendación

| Pieza | Qué es | Recomendación |
|---|---|---|
| **(a) Por la planilla**, como el bono por meta | La comisión entra a la línea de cada persona en la planilla quincenal; la planilla hace sus asientos, su comprobante y su pago. | **Sí**, es lo que se pidió («o desde nómina») y deja un solo lugar donde se ve todo el dinero de la persona. |
| **(b) En las fechas que Gerencia defina** | Cada propuesta lleva «se paga en la planilla que termina el…». De fábrica: la primera quincena del mes siguiente, como el bono por meta (A2). Otras opciones: la segunda quincena, o la fecha que Gerencia ponga. | **Primera quincena del mes siguiente** al cierre, para dar tiempo a revisar y aprobar. |
| **(c) Propuesta → revisión → aprobación** | El sistema arma la propuesta del mes; Gerencia o contabilidad la revisa y ajusta con motivo; al **aprobarla** recién se mueve el dinero. | **Sí, y que nada se pague solo.** Ningún proceso automático aprueba ni paga. |

### El camino de una propuesta

1. **Borrador.** El día 1 de cada mes, de madrugada, el sistema sella el estado del mes que terminó (sección 7) y arma la
   propuesta con una fila por persona: *saldo que arrastra* + *lo del mes* = *a pagar*. Si el saldo de alguien es
   negativo (devoluciones que superaron lo ganado), se propone **cero** y el saldo negativo sigue al mes siguiente:
   nunca se le cobra a alguien por la planilla sin que Gerencia lo decida.
2. **Revisada.** Gerencia o contabilidad la miran. Cualquier ajuste (por ejemplo por una salida a mitad de mes) es una
   fila de **ajuste con motivo y autor** en el libro; no se pisa nada.
3. **Aprobada.** La aprueba **una persona de Gerencia que no figura entre quienes reciben** (sección 7). Queda quién, cuándo
   y la huella de lo aprobado. Al aprobar se anota en el libro una fila de **liquidación** (negativa) por persona: el
   saldo baja y esa plata ya no puede entrar en otra propuesta.
4. **En planilla → Pagada.** La planilla quincenal la toma al calcularse y la paga cuando se confirma y se paga; ahí
   cambia a «Pagada». Quien está fuera de planilla se marca **pagada fuera de planilla** con fecha y referencia.
5. **Cancelada** (antes de confirmar la planilla): se anula con una fila contraria y la plata vuelve al saldo.

Hay **dos llaves antes de que salga un centavo**: la aprobación de la propuesta y la confirmación de la planilla (que
exige las tasas validadas por el contador y no se paga dos veces el mismo periodo: A2).

### Qué hace falta en `dcasa_nomina`

Hoy la planilla ya sabe pagar «como salario» (el bono por meta y «otros ingresos») y «sin descuentos» (los reembolsos). Se
agregan, imitando al bono por meta (A2):

1. En la línea de la planilla (`dcasa.nomina.linea`): un campo `comision_web` (solo lectura) y la relación con las
   líneas de propuesta que lo forman.
2. `_enlazar_comision_web()`, llamado junto a `_enlazar_bonos()` al calcular: toma las propuestas **aprobadas y todavía no
   enlazadas** de cada persona cuya fecha de pago sea anterior o igual al fin de esa quincena (como los
   reembolsos), y las **suelta** si la planilla se cancela o la persona sale.
3. El cálculo de la línea (`_compute_importes`) según el tratamiento que quedó **congelado en la propuesta**: **salario**
   → suma a lo devengado y paga cuotas e impuesto como lo extra (como el bono por meta); **sin descuentos** → suma al neto
   sin cuotas ni impuesto (como los reembolsos); **fuera de planilla** → no entra.
4. El asiento: el gasto va a la cuenta de sueldos (salario) o a una **cuenta nueva** de la configuración de la nómina
   (`cuenta_comision_web_id`) para el resto, o también para el salario si la contadora quiere verla aparte.
5. El comprobante de pago: un renglón «Comisión del sitio web» (como el del bono por meta).

**Cómo se evita pagar dos veces** (cinco candados): una propuesta aprobada es única por persona y mes
(restricción de base de datos); cada línea de propuesta solo puede estar en **una** línea de planilla; la liquidación
baja el saldo en el momento de aprobar; el sistema no deja aprobar una propuesta de un mes cuyo estado no esté sellado; y
una planilla cancelada solo **suelta** (no borra) lo que tomó.

## 7. Conflicto de interés y confianza

**Quienes reciben esta comisión también construyeron el sistema y lo administran.** Eso no es una acusación: es
exactamente la situación en la que una cifra necesita controles para valer ante Gerencia general y ante la contadora. Estos
son los que propongo, de lo más fuerte a lo más flojo, y al final lo que **no** se puede evitar.

### Lo que sí se puede hacer

1. **Quién cambia reglas y porcentaje: solo Gerencia, y no por ser administrador técnico.** El programa de vendedores deja
   ajustar a Gerencia **y** a los administradores técnicos (A3); aquí no: un administrador sin el rol de Gerencia no ve
   ni cambia las reglas.
2. **Dos llaves.** Gerencia **propone** una versión de las reglas, una lista de quienes reciben o una propuesta de pago;
   las **aprueba** alguien con un grupo aparte, «Aprueba la comisión web», que **no figure en la lista de quienes
   reciben**. El servidor lo exige (la pantalla no es de confianza). Para que funcione, **Gerencia general necesita su
   propio usuario** (P7). Opcional: exigir que quien aprueba tenga puesto el segundo factor (Odoo guarda si lo tiene).
3. **Libro sin edición ni borrado.** Las filas no se editan ni se borran, ni por pantalla ni por RPC (se prueba); una
   corrección es otra fila con motivo y autor. Las reglas aprobadas tampoco se editan (A3).
4. **Registro de cambios.** Quién propuso y quién aprobó cada versión y cada propuesta de pago, cuándo, y qué cambió
   frente a la anterior. Una pantalla **«Quién puede cambiar esto»** lista a las personas con el rol de Gerencia, con la
   llave de aprobación y con el rol de administrador técnico.
5. **Estado mensual congelado con huella (sello).** El día 1, de madrugada (con margen para pagos que estén en vuelo),
   el sistema sella el mes que terminó: guarda cuántas filas, la base, el total, el porcentaje que rigió, el reparto,
   **quiénes tenían la llave de aprobación** y una **huella** (SHA-256) calculada sobre todas las filas del mes **más la
   huella del mes anterior**. Así cambiar un mes viejo obligaría a recalcular todas las huellas siguientes. El sello y el
   PDF del estado se mandan por correo a **Gerencia general y a la contadora** (no a quienes reciben) y se muestran
   en pantalla. Un botón **«Verificar contra el libro»** vuelve a calcular la huella y dice si coincide. Un mes sellado
   **nunca se reabre**: un error se corrige con filas en el mes abierto. (Para el correo hay que sumar una clase nueva
   a la política de `dcasa_correo`, que respeta el mismo interruptor y no sale en staging: A12.)
6. **Testigo de origen que no se puede cambiar.** Cada pedido nuevo guarda en una marca de solo escritura si **nació en
   la web**. Hoy `website_id` se puede cambiar por código y con él el origen del pedido (A6, A13). La comisión exige
   las dos cosas, los pedidos que ya existían al instalar se marcan una sola vez en ese momento, y un cambio posterior
   de `website_id` en un pedido que ya contó dispara una **alerta** en el estado.
7. **Ni compras propias ni pedidos fantasma sin rastro.** Las compras de quienes reciben no cuentan (A3). Cada fila
   muestra **cómo se pagó** y **si ese pago está conciliado con el banco**, y el sello dice qué parte de la base está
   conciliada. Un pedido que se paga y se devuelve se reversa solo.
8. **Mirar quién arma las campañas y los precios.** Quienes reciben también pueden tocar precios y campañas del sitio
   (solo Gerencia y quienes cambian precios, A14). No inflan la base (el cliente tiene que pagar), pero sí pueden
   cambiarla para bien o para mal. Por eso el estado muestra el **precio cobrado** y el sello **no esconde** los
   meses de campaña. Cualquier cambio de campaña ya queda en su historial.
9. **Un error de la comisión nunca frena una venta ni un cobro** (sección 9).
10. **Revisión independiente.** Antes de usarlo, la contadora (o alguien de afuera) revisa las reglas, el reparto y el
    primer sello; después, cada vez que cambie algo de eso. El código vive en un repositorio con pruebas y pasa por
    revisión adversarial (sección 9).

### Lo que NO se puede evitar (con franqueza)

- **Un administrador técnico siempre puede tocar la base de datos**, cambiar el código desplegado, quitar un control o
  darse un rol. La huella no lo impide: lo hace **visible**, y solo si Gerencia general **conserva los correos de cada
  mes y alguien los compara**. Si nadie compara, el sello no sirve de nada.
- **Si quien recibe controla el correo o el teléfono de quien aprueba**, las dos llaves se vacían. El correo del sello
  tiene que ser de una cuenta que quienes reciben **no controlen**.
- **Pedidos y pagos falsos.** Alguien con permisos podría crear un pedido por la web y registrar un pago que no ocurrió.
  La conciliación con el banco, la devolución automática de lo que se revierte y la visibilidad del estado lo hacen
  **detectable**, no imposible. En «Pago en la tienda» el efectivo no se concilia con ningún banco: es el punto más
  flojo, y otro motivo para que Gerencia decida con calma esa opción (P3).
- **El código lo escriben los mismos que cobran.** El repositorio es público, tiene pruebas y revisión adversarial, pero
  no es independencia total: por eso el punto 10 (revisión de afuera).
- Los respaldos que ya existen (copia diaria y cambios en el almacenamiento de Cloudflare) sirven para **comparar contra
  una fecha anterior** si hay sospecha, pero están bajo el mismo control técnico.

La regla práctica: **la cifra vale tanto como la costumbre de Gerencia de mirar el sello cada mes.** El sistema hace que
mirar sea fácil y que cambiar algo en silencio deje rastro; no puede obligar a mirar.

## 8. Lo legal y contable (preguntas para la contadora y el abogado)

**Este documento no afirma ninguna tasa, fecha ni artículo, y no se buscó nada en la web: son preguntas.** Quien
responde es la contadora o el abogado, no el sistema.

### Qué hace el sistema hoy con el bono por meta (se lee del código)

El bono por meta se trata **como salario** (A2, y lo dice el propio código: «REQUIERE CONTADOR»):

- Suma a lo **devengado** de la línea y paga **seguro social** (trabajador y patrono), **seguro educativo**, **riesgo
  profesional** del patrono e **ISR** como lo extra de esa quincena (no se proyecta al año).
- Entra en la **base del décimo tercer mes** (que suma lo devengado de las planillas confirmadas) y en la
  **provisión del décimo** (una parte de lo devengado de esa misma planilla, si la contadora la activa).
- Entra en el **promedio de los últimos 11 meses** que usan las **vacaciones** y la **prima de antigüedad**, solo si la
  persona ya tiene planillas confirmadas de ese tiempo; si no, el cálculo usa su salario mensual.
- Sale en el comprobante de pago como «Bono por meta de ventas».

Para la comisión web habría que elegir una de **tres formas de pagar**, y el sistema las soporta con una opción que se
guarda **congelada en cada propuesta** (por eso se puede cambiar sin reprogramar):

| Forma | Qué pasa en la planilla |
|---|---|
| **Como salario** (hoy, el bono por meta) | Paga cuotas e impuesto, entra en décimo, vacaciones y prima. |
| **Sin descuentos** (hoy, los reembolsos) | Se suma al neto, no paga cuotas ni impuesto, no entra en décimo ni vacaciones. |
| **Fuera de planilla** | No entra a la planilla; se paga aparte y el sistema anota la referencia. |

Mientras la opción esté vacía el sistema **mide y propone, pero no deja aprobar un pago**.

### Preguntas para la contadora

1. Esta comisión (un porcentaje de lo vendido por el sitio, variable y mensual): ¿es **salario** para la nómina? Si lo
   es, ¿entra en la base de seguro social, seguro educativo, riesgo profesional, ISR, décimo tercer mes, promedio de
   vacaciones y prima de antigüedad, como hoy el bono por meta?
2. Si **no** es salario (bono o gratificación): ¿en qué condiciones, con qué papel firmado y con qué retención de ISR, si
   la hay? ¿Cómo se declara?
3. Si alguien de la lista **no está en planilla** (socio o por honorarios): ¿cómo se le paga y qué documento lleva?
4. ¿Qué **cuenta contable** lleva el gasto? ¿Se acumula (provisión) en el mes en que se vende, o se reconoce al pagar,
   como hoy el bono por meta?
5. El método de retención de ISR de la planilla (proyección anual, y lo extra como adicional): ¿sirve para una comisión
   mensual?
6. ¿La base correcta para el gasto es la del estado (sin ITBMS y sin envío), o la factura completa?

### Preguntas para el abogado

1. ¿Hay que formalizar la comisión por escrito (adenda o acuerdo)? ¿Qué debe decir: base, porcentaje, cuándo se paga,
   qué pasa si la persona se va?
2. Una comisión que se paga todos los meses y varía, aunque se llame bono: ¿genera derechos por habitualidad? ¿Se
   puede cambiar o quitar hacia adelante, y con qué aviso?
3. Si una venta se **devuelve después de pagada** la comisión: ¿se puede descontar de la planilla siguiente, con qué
   consentimiento y hasta qué parte? (El sistema hoy no descuenta nada solo: lo deja como saldo negativo que se arrastra.)
4. ¿Qué pasa con la comisión pendiente cuando alguien renuncia o termina la relación (liquidación)?

## 9. La propuesta de construcción

Se construye en **tres fases** (la fase 1 es este documento). El trozo más pequeño, que da **medición y transparencia sin
pagar nada solo**, es la fase 2:

- **Fase 2 (MVP): medir y mostrar.** Reglas, ventas del sitio, libro, estado mensual, sello. **No paga nada y no toca
  la planilla.** Se puede construir ya: no depende del dictamen legal.
- **Fase 3: propuesta, revisión y aprobación.** Las dos llaves y el registro del pago fuera de planilla.
- **Fase 4: enlace con la planilla.** Solo después del dictamen (P8) y de elegir cómo se trata al pagar.

### 9.1 Qué se construye (módulo nuevo `dcasa_comision_web`)

Depende de `dcasa_base`, `dcasa_nomina`, `dcasa_interfaz` (el origen), `dcasa_invoice` (para reconocer el flete) y
`website_sale`. Ningún campo en modelos de Odoo sin el prefijo `dcasa_`.

| Modelo | Para qué | Notas |
|---|---|---|
| `dcasa.web.reglas` + `dcasa.web.reparto` | Una versión de las reglas y su lista de personas con su % de reparto | Porcentaje y tratamiento **vacíos**; las cuatro decisiones de la sección 2; estados borrador/aprobada; aprobada no se edita ni se borra; «rige desde» solo hacia adelante (patrón de `dcasa.vend.reglas`, A3); la suma del reparto es 100 %. **Sin registros de fábrica**: el módulo nace sin versiones. |
| `dcasa.web.venta` | Una fila por factura que cuenta o está en duda | Congela base, porcentaje, versión, cómo se pagó, conciliación, vendedora, referencias. Un índice único evita dos filas activas de la misma factura (patrón de `dcasa.vend.comision`, A3). Si no hay versión vigente: se mide y no genera filas de libro. |
| `dcasa.web.movimiento` | **El libro**, por persona, en centavos enteros | `write` y `unlink` bloqueados; restricción `monto <> 0`; `reversa_id` único; motivo obligatorio en ajustes y reversos; el mes de Panamá se guarda calculado; **una sola puerta de entrada** (`_asentar`). Saldo = suma (patrón de `dcasa.vend.movimiento`, A3). |
| `dcasa.web.cierre` | El sello de cada mes | Mes único por empresa; huella y huella anterior; a quién se mandó y cuándo; no se edita. |
| `dcasa.web.propuesta` + líneas (fase 3) | La propuesta de pago y su aprobación | Único por persona y mes; estados de la sección 6; quién aprobó. |
| `sale.order.dcasa_nacio_en_web` | El testigo de origen | Se escribe al crear; no se puede cambiar; se marca una vez a los pedidos que ya existen. |

### 9.2 Qué cálculo corre y cuándo (y por qué nunca frena una venta)

1. **Al quedar pagada una factura** (gancho `_invoice_paid_hook`, que Odoo llama tras conciliar, A13): se anota la venta
   y las filas del libro. Va **dentro de un savepoint** y con el error al registro, exactamente como la comisión de
   vendedores (A3): **un error o un tope de la comisión nunca hace fallar un cobro ni una factura**. El gancho puede
   llamarse más de una vez (de «en proceso de pago» a «pagada»): es idempotente.
2. **Cada noche, un barrido** que (a) anota las facturas del sitio pagadas que no tienen venta (un gancho que falló),
   (b) **compara el libro con la verdad** de cada venta —devoluciones, notas aplicadas sueltas, pago revertido,
   factura cancelada o vuelta a borrador— y asienta la **diferencia** como fila contraria, y (c) arma las
   alertas. Comparar con la verdad (en vez de reaccionar a eventos sueltos) es lo que cubre las notas de crédito que
   se aplican sin enlazar, lo que el bono por meta ya hace (A1).
3. **El día 1, de madrugada** (hora de Panamá): corre el barrido, **sella el mes** y arma la propuesta (fase 3).
4. La definición de «pagada por completo y qué día» **ya existe dos veces** en el sistema (bono por meta y «Completadas»
   del Inicio, A5). No hacer una tercera copia: **reutilizar una y agregar una prueba que verifique que las dos dan lo
   mismo**.
5. Sin porcentaje vigente en el momento de anotar, la venta se mide y **no genera filas de libro**: lo medido antes de
   la primera versión no cobra nunca (solo hacia adelante).

### 9.3 Pantallas y dónde viven

Una **app propia «Comisión del sitio web»** (como «Mis gastos por reembolsar», no dentro de Nómina): quienes reciben
no tienen la Nómina ni Ventas, y la comisión no debe depender del departamento.

- **Estado del mes** (la pantalla de abrir): el estado de la sección 5, con Excel (como los reportes contables, A12) y PDF
  (como los comprobantes, A12).
- **Ventas del sitio**: la lista de ventas con sus filtros y enlace a factura y pedido (Gerencia).
- **Libro** y **Sellos** (Gerencia y aprobadores): el libro con sus filtros y los sellos con «Verificar».
- **Configuración › Reglas** y **Quién puede cambiar esto** (Gerencia).
- Fase 3: **Propuestas**. Fase 4: nada nuevo en esta app (lo demás vive en Nómina).

### 9.4 Permisos

| Grupo | Qué puede |
|---|---|
| Gerencia (`dcasa_base.group_gerencia`) | Todo, **menos aprobar**: propone versiones, listas y propuestas, y hace ajustes con motivo. |
| «Aprueba la comisión web» (grupo nuevo; **no** lo incluye Gerencia ni el administrador técnico) | Ve todo en solo lectura y aprueba versiones, listas y propuestas, **si no figura entre quienes reciben**. |
| «Recibe la comisión web» (grupo nuevo, solo lectura; el módulo lo da a las personas de la lista vigente) | Ve **su** parte y el estado general, sin nombres de clientes. |
| Administrador técnico solo (`base.group_system`) | **Nada** de la comisión (puede, como siempre, asignarse roles: es el límite honesto de la sección 7). |

Hay regla de registros para que cada quien vea lo suyo y regla de empresa (como el resto de los modelos de nómina, A4). Los
botones llaman a métodos que **comprueban el grupo en el servidor** y ninguno recibe `@api.model` (la lista llama con ids). Los
métodos nuevos se suman a la `LISTA_BLANCA` de `dcasa_base/tests/test_superficie_rpc.py` solo si deben ser públicos.

### 9.5 Pruebas que hacen falta

Una prueba por cada decisión de la tabla de la sección 2, con **cifras de prueba creadas por la propia prueba**:

1. **Qué cuenta:** pedido web pagado por cada tipo de diario (pasarela de prueba, transferencia, caja); chatbot y vendedora
   **no**; factura mixta (solo líneas web); envío, ITBMS y flete fuera de la base; descuento y premio de Socios dentro del
   neto; compra de una persona de la lista fuera; factura histórica y anterior a la primera versión fuera.
2. **Sin porcentaje:** la venta se mide, no hay filas de libro; con la primera versión, solo lo posterior cobra.
3. **Versiones:** solo hacia adelante, no se editan ni se borran, el reparto suma 100 %, las cuatro decisiones son
   obligatorias y los centavos del reparto cuadran siempre.
4. **Libro:** `write` y `unlink` bloqueados (también por RPC), reverso único, saldo = suma, mes de Panamá en los bordes
   (`freezegun`), una devolución usa las partes originales.
5. **Reversos:** nota parcial y total, nota aplicada suelta, pago revertido, factura a borrador y cancelada, idempotencia
   del gancho y del barrido, un mes sellado no cambia.
6. **Savepoint:** forzar un error al anotar y comprobar que el cobro y la nota de crédito igual se publican.
7. **Permisos:** quien recibe ve lo suyo y nada más; vendedora, Caja y Marketing no ven ni el menú ni por enlace; el
   administrador técnico solo no puede cambiar reglas; **quien recibe no aprueba** (versión, lista ni propuesta);
   no se puede escribir el testigo de origen.
8. **Sello:** la huella se reproduce; si una prueba cambia una fila a mano (SQL), «Verificar» lo detecta; la cadena
   depende del mes anterior.
9. **Testigo de origen:** cambiar `website_id` después de crear no crea comisión y dispara la alerta.
10. **Excel y PDF:** se generan, con los totales del estado; el de quien recibe no trae nombres de clientes.
11. **Pantallas en el navegador** a 1440 y 390 px (como `test_pantallas_nomina.py`) y capturas para Gerencia.
12. Fase 4, en `dcasa_nomina`: lo mismo que ya prueba el bono por meta (entra en la primera quincena, no se paga dos
    veces, cancelar la planilla suelta, comprobante) para los tres tratamientos.

### 9.6 Guía, Brian, documentos e instalación

- **La Guía** (`addons/dcasa_guia/data/guia.json`): una tarea por pantalla («Ver el estado de comisión del sitio web»,
  «Proponer un cambio de porcentaje», «Armar y aprobar la propuesta del mes», «Verificar el sello del mes»), en palabras
  sencillas y **sin cifras**. Se escribe **cuando existan los menús**: si no, las pruebas de la Guía fallan porque el
  destino no existe.
- **Brian** (docs/BRIAN.md): una herramienta de **solo lectura** para Gerencia, «estado de la comisión del mes»; sin
  herramientas que aprueben ni paguen.
- Documentos: `docs/COMISION_WEB.md` (cómo se usa), `docs/PERMISOS.md` (las dos llaves) y `docs/MODULOS.md`.
- **Instalación:** el módulo se suma a la lista `MODULES` del `Makefile` y a `ODOO_MODULES` de `docker/entrypoint.sh`
  (si no, el contenedor de producción no lo instala).

### 9.7 Revisión adversarial (la pide el dinero y los datos de empleados)

Con revisor independiente y con la lista de ataques: **aprobar la propia comisión**; **cambiar el origen de un pedido**;
**pagar dos veces** (dos propuestas, dos planillas, planilla cancelada y vuelta a calcular); montos negativos o
redondeos que no cuadran; el borde del mes y de la hora; llamar los métodos por RPC o con `sudo`; ver lo de otra
persona; un error tragado en el savepoint que esconda ventas (por eso las alertas); cambiar un mes sellado por SQL;
carreras entre el barrido y el gancho (un candado, como el de numeración de `dcasa.vend.reglas`, A3).

### 9.8 Pasos, en orden

| # | Paso | ¿Depende de una decisión? |
|---|---|---|
| 1 | Módulo, `dcasa.web.reglas` y `dcasa.web.reparto` (sin ninguna versión de fábrica) y sus permisos | Libre |
| 2 | Testigo de origen (`dcasa_nacio_en_web`) y marcado único de lo que ya existe | Libre |
| 3 | `dcasa.web.venta` + gancho de pago + barrido nocturno: **solo medir** (sin libro) | Los criterios fijos son libres; las **cuatro decisiones** de la sección 2 (P3) quedan como parámetros sin responder |
| 4 | Libro `dcasa.web.movimiento`, reversos y devoluciones | P2 (base y momento); P1 (para que cobre algo) |
| 5 | Estado del mes (pantalla, Excel, PDF) y alertas | P5 (quiénes reciben y qué ve cada quien) |
| 6 | Sello mensual, huella encadenada, «Verificar» y correo | P7 (quién aprueba y a quién le llega el sello) |
| 7 | Pruebas, capturas en computadora y celular, Guía, Brian y documentos | — |
| 8 | **Revisión adversarial**; CI con staging; producción | Aprobación de Gerencia |
| 9 | **Fase 3:** propuesta, revisión y aprobación; «pagado fuera de planilla» | P6 y P7 |
| 10 | **Fase 4:** enlace con la planilla (`dcasa_nomina`) para los tres tratamientos y su revisión | **P8: dictamen de la contadora y el abogado** |

### 9.9 Riesgos y lo que hay que verificar al construir

- La pasarela (Tilopay) se hace en otra rama y **todavía no existe**: la comisión solo necesita que su pago quede aplicado a
  la factura y registrado en su diario. Comprobarlo cuando esa rama llegue, con un pago de prueba.
- Un pedido de la web **entra sin vendedora**, y la vendedora que lo confirma se lo queda (A6): ese mismo pedido cuenta
  para su bono por meta. Ver P4.
- El pago «en proceso de pago» cuenta (como en el bono por meta); el barrido nocturno reversa si el pago se cae.
- El envío que suma el chat de la tienda puede desaparecer al pagar (A8): por eso queda fuera de la base.
- Una factura de un mismo pedido en varias entregas se cuenta cada una al quedar pagada.

## 10. Preguntas para Gerencia general

Ocho preguntas, cada una con su recomendación y lo que pasa con cada respuesta. Las **P1 a P5** hacen falta para empezar a
construir el módulo; las **P6 a P8**, antes de que se pague el primer centavo. **Ninguna pide un número**: el porcentaje y las
personas los escribe Gerencia general en la pantalla de reglas, cuando quiera.

**P1. ¿Cómo se define la comisión?**
- **A (recomiendo): un porcentaje fijo sobre toda la base del sitio.** Fácil de entender, de medir y de explicar.
- B: un porcentaje que solo se gana si el sitio llega a una meta del mes (como el bono por meta de las vendedoras).
- C: porcentajes distintos por tipo de producto.
- Efecto: con A el estado es una sola cuenta; B y C obligan a reglas más largas y más cosas que discutir. B y C quedan
  para el futuro (sección 11).

**P2. ¿Sobre qué monto, y cuándo cuenta una venta?**
- **A (recomiendo): lo que entró, sin ITBMS, con los descuentos puestos y menos las devoluciones, y solo cuando la factura
  queda pagada por completo.** Una devolución resta en el mes en que ocurre, y si deja saldo negativo se arrastra. (El
  envío se decide aparte, en P3.)
- B: contar la venta al confirmar el pedido, aunque todavía no se haya cobrado.
- C: contar por cada abono, en proporción.
- Efecto: A es lo más limpio y lo que ya hacen el bono por meta y el programa de vendedores. B paga por ventas que pueden
  no cobrarse nunca. C obliga a deshacer pedazos si hay una devolución.

**P3. ¿Qué pasa con los casos dudosos?** (cada uno es un interruptor que se contesta una vez, en la pantalla de reglas)
- **«Pago en la tienda»** (pedido de la web que se paga en el local): **A (recomiendo): cuenta**; B: no cuenta; C: cuenta solo
  si paga dentro del plazo del apartado.
- **Chatbot de WhatsApp (Juan):** **A (recomiendo): no cuenta** (es otro canal); B: cuenta.
- **Envío:** **A (recomiendo): no cuenta**; B: cuenta. **Comisión de la pasarela:** **A (recomiendo): no se resta**; B: se resta
  cuando cada pago la guarde.
- Los demás casos de la tabla de la sección 2 (devoluciones, descuentos y premios de Socios, precio de campaña, ITBMS)
  siguen mi recomendación **salvo que Gerencia diga lo contrario**.
- Efecto: sin respuesta, esas ventas aparecen «en duda» y no suman; se ve cuánto dinero depende de cada una.

**P4. Cuando una vendedora atiende o confirma un pedido de la web, ¿ese pedido cuenta también para su meta?**
- **A (recomiendo, para empezar): sí, para las dos** (es lo que pasa hoy con la meta). La empresa paga dos incentivos por
  esa venta, y el estado muestra cuántas ventas son así para decidir con datos.
- B: solo comisión del sitio; la venta sale de la meta de la vendedora (le cambia su bono: hay que avisarle y decidir).
- C: solo meta de la vendedora.
- Efecto: A no cambia nada de lo que ya cobran las vendedoras. B y C sí, y conviene decidirlo con las cifras reales del estado.

**P5. ¿Quiénes reciben, cómo se reparten y qué ve cada quien?**
- Gerencia general escribe la lista (empleados) y el reparto (que suma 100 %). **Recomiendo** que cada persona vea el estado
  completo y **su** parte, y no la parte de otra; y que no vea nombres de clientes.
- Opciones del reparto: **A:** partes iguales; **B:** partes distintas que Gerencia fija; **C:** según lo que cada quien
  aporta (no se puede medir sin inventar; **no recomiendo**).
- Efecto: A y B se guardan como versión y se cambian hacia adelante; la salida o entrada de alguien a mitad de mes se
  resuelve con una versión nueva y, si hace falta, con un ajuste con motivo.

**P6. ¿Cómo y cuándo se paga?**
- **A (recomiendo): por la planilla, en la primera quincena del mes siguiente al cierre, y solo con propuesta aprobada.**
- B: por la planilla en otra fecha que Gerencia ponga (fin de mes, segunda quincena).
- C: fuera de planilla (honorarios), con referencia de cada pago.
- Efecto: A es lo que pidió el equipo y lo que ya hace el bono por meta. C no necesita cambios en la planilla pero el
  dinero se mueve fuera del sistema. Para quien no está en planilla, C es la única salida.

**P7. ¿Quién aprueba, y a quién le llega el sello de cada mes?**
- **A (recomiendo): Gerencia general, con su propio usuario, aprueba; el sello llega a Gerencia general y a la contadora.**
  El sistema **no deja aprobar a quien recibe**.
- B: la contadora aprueba y Gerencia general solo recibe el sello.
- C: cualquiera de Gerencia (**no recomiendo**: una persona de Gerencia puede ser quien recibe).
- Efecto: A y B hacen que la cifra valga ante terceros. C deja la llave en manos de quien cobra. Con A, Gerencia general
  necesita un usuario propio en el sistema y una cuenta de correo que quienes reciben no controlen.

**P8. ¿Se pide el dictamen de la contadora y del abogado antes de pagar la primera comisión?**
- **A (recomiendo): sí.** Mientras tanto el sistema mide, propone y sella; **no se aprueba ningún pago** hasta que la forma de
  tratarlo (salario, sin descuentos o fuera de planilla) esté contestada.
- B: pagar la primera como el bono por meta (como salario) y confirmar después.
- Efecto: A retrasa el primer pago pero evita pagar mal y tener que corregir cuotas, décimo y renta. B corre el riesgo de
  corregir después planillas ya confirmadas.

## 11. Lo que NO se hará ahora

Anotado como futuro, para no inflar esta primera versión:

- **Escalones o metas** del sitio (un porcentaje distinto si el mes llega a cierto nivel) y **topes** mensuales o por
  factura.
- **Bonos por canal:** chatbot de WhatsApp, tienda física, otras pasarelas con porcentajes propios.
- **Porcentajes por categoría o producto.**
- **Pago quincenal** de la comisión (hoy solo la propuesta mensual).
- **Retención por devoluciones:** esperar unos días antes de proponer lo vendido (como los puntos de vendedores).
- **Restar la comisión de la pasarela** por cada venta (hoy solo el interruptor, apagado).
- **La web como sucursal completa** (resultados propios: ventas, costos y comisión del sitio en una cuenta analítica
  aparte), aprovechando los datos que este estado ya junta.
- Un resumen de la comisión en el **Inicio** y avisos automáticos por Telegram.
- **Aprobar o pagar automáticamente**: no se hará nunca sin una decisión explícita de Gerencia general.

## Anexo A. De dónde sale cada dato (archivo y línea)

Verificado contra el código de la rama `local/comision` (base `32cc9b2`) el 2026-11-19. Si algo no coincide con el
código, manda el código. Las rutas son desde la raíz del repositorio.

| Id | Qué | Dónde |
|---|---|---|
| **A1** | **El bono por meta** | |
| | Quién participa (marca del departamento y usuario) | `addons/dcasa_nomina/models/meta_ventas.py:52` y `:192-196` |
| | Qué cuenta: facturas del «Vendedor», pagadas, no históricas, desde la primera meta | `meta_ventas.py:225-264` (el filtro, `:239-242`) |
| | Día de cobro (la última conciliación, nunca antes de la factura) | `meta_ventas.py:198-223` |
| | Cada venta cuenta una sola vez; mes ya cerrado pasa al siguiente | `meta_ventas.py:266-288` |
| | El bono: el porcentaje de TODO lo cobrado si llega a la meta; cron diario | `meta_ventas.py:294-320`, `:329-335` |
| | La meta con vigencia por mes, solo hacia adelante | `meta_ventas.py:68-130` (restricción `:96-111`) |
| | Pantallas, datos de fábrica y cron (las cifras que dio el jefe no se repiten aquí) | `addons/dcasa_nomina/views/meta_ventas_views.xml:4-166`, `data/meta_ventas_data.xml:10-31` |
| | Cómo lo explica la documentación | `docs/NOMINA.md:150-187` |
| **A2** | **Cómo entra algo a la planilla y cómo trata la nómina un bono** | |
| | `otros_ingresos` y `comision_meta` en la línea | `addons/dcasa_nomina/models/planilla.py:541-546` |
| | El bono suma a lo devengado, paga cuotas y aportes del patrono, y el ISR como lo extra; el neto | `planilla.py:592-631` (`:600-603`, `:613-618`, `:619-627`, `:630-631`) |
| | Provisión del décimo sobre lo devengado | `planilla.py:406-409` |
| | Entra en la **primera** planilla quincenal del mes (`día 1`); se llama al calcular | `planilla.py:252-289` (`:263`), `:235` |
| | Los reembolsos entran «sin descuentos» y por fecha | `planilla.py:291-299` (`:297`), `:393-396`, `:630` |
| | Soltar lo enlazado al cancelar o salir de la planilla | `planilla.py:512`, `:636-638` |
| | Quién entra en una planilla (ingreso y salario) | `planilla.py:161-179` |
| | No se paga dos veces el mismo periodo; confirmar exige tasas validadas | `planilla.py:123-141`, `:423-426` |
| | Base del décimo y promedio de 11 meses (vacaciones y prima) | `addons/dcasa_nomina/models/hr_employee.py:50-61`, `:63-78`; `liquidacion.py:97` |
| | Renglones del comprobante de pago | `addons/dcasa_nomina/report/nomina_reportes.xml:65-68` |
| | Cuentas contables de la nómina | `addons/dcasa_nomina/models/config.py:12-23`, `:54-56`, `:94-102` |
| | La regla de oro: las tasas las valida el contador | `docs/NOMINA.md:8-41` |
| **A3** | **El programa de vendedores (el patrón de dinero bien hecho)** | |
| | Quién puede ajustar (Gerencia **y** administradores técnicos) | `addons/dcasa_socios/models/vend_reglas.py:27` |
| | La versión no se edita ni se borra; solo hacia adelante; candado de numeración | `vend_reglas.py:99-126` |
| | `_vigentes()` nunca falla | `vend_reglas.py:172-182` |
| | Libro: restricciones, sin editar ni borrar, reverso, saldo = suma | `addons/dcasa_socios/models/vend_movimiento.py:50-52`, `:60-66`, `:79-86`, `:89-94` |
| | Comisión con campos congelados e índice único por factura | `addons/dcasa_socios/models/vend_comision.py:44-95` |
| | Compra propia y otras razones de «no se paga» | `vend_comision.py:17-32`, `:306-` |
| | Revisión nocturna de pagos revertidos; anular con asiento contrario; devolución parcial | `vend_comision.py:380-394`, `:396-416`, `:418-427` |
| | El gancho de pago con savepoint y las notas de crédito | `addons/dcasa_socios/models/account_move_vend.py:36-47`, `:77-92` |
| | Las reglas no negociables | `CLAUDE.md` («Programa de vendedores»); `docs/VENDEDORES.md:142-` |
| **A4** | **Permisos y roles** | |
| | El grupo «Administra la nómina»; Gerencia lo incluye; reglas de empresa | `addons/dcasa_nomina/security/nomina_security.xml:7-26`; `security/ir.model.access.csv` |
| | Quién ve qué (la vendedora no ve nómina) y mapa de roles | `docs/PERMISOS.md:3`, `:480-490` |
| **A5** | **«Pagada por completo, y qué día»: ya está dos veces** | `meta_ventas.py:198-223` y `addons/dcasa_interfaz/models/ventas_bases.py:15-17`, `:302-` |
| **A6** | **El origen Web / Chatbot / Vendedora** | |
| | Cómo se calcula (de `website_id`) y cómo hereda la factura (prioridad chatbot, web, vendedora) | `addons/dcasa_interfaz/models/origen.py:14-15`, `:27-30`, `:36-47` |
| | Lo que arma Juan es «Chatbot» | `addons/dcasa_conversaciones/models/sale_origen.py:101-106` |
| | Etiquetas y filtros en las listas | `addons/dcasa_interfaz/views/origen_views.xml:4-96` |
| | Los pedidos de la web entran **sin vendedora**; la que confirma se lo queda | `addons/website_dcasa/models/pedido_web.py:1-15`, `:31-45` |
| | `website_id` solo está de solo lectura en la pantalla | `vendor/odoo/addons/website_sale/models/sale_order.py:24-28` |
| **A7** | **Cómo llegan los pagos** | |
| | Hoy no hay pasarela: Yappy y transferencia a mano, o pago en la tienda | `addons/website_dcasa/models/tienda.py:1-12`, `:17-30` |
| | Diarios de cobro (Efectivo, Yappy, Tarjeta) y financieras (Tafi, Crediviva) | `addons/dcasa_base/__init__.py:12-24` y `:21-` |
| | Tilopay: en otra rama, todavía no existe | `docs/PRIORIDADES.md:149-151` |
| **A8** | **Andrés y el carrito real** | `docs/BRIAN_TIENDA.md:12-14`, `:29-35`, `:72-83`, `:103-112` |
| **A9** | **La base: premios, envío e ITBMS** | |
| | Socios mide sin la línea del premio y sin envío ni flete | `addons/dcasa_socios/models/sale_order.py:156-165`; `docs/SOCIOS.md:62` |
| | Cómo se reconoce un flete o un envío | `addons/dcasa_invoice/models/lineas.py:88-110`; `is_delivery` en `vendor/odoo/addons/delivery/models/sale_order_line.py:9` |
| | Criterio contable (ventas sin ITBMS; dinero con ITBMS) | `docs/LEEME_PRIMERO.md:27` |
| **A10** | **Apartados y abonos** | `addons/website_dcasa/models/sale_order.py:1-19`, `:111-119`; `docs/OPERACION.md:1212-1240`; `docs/DECISIONES_CONTABLES.md` (A3) |
| **A11** | **La atribución «en tres» del chatbot** vive en el panel de Juan (no en el tablero del Inicio) y mira 30 días | `addons/dcasa_conversaciones/models/panel_juan.py:337-398`; `panel_calculos.py:19-21` |
| **A12** | **Precedentes que se reutilizan** | |
| | Política de correos (clases permitidas) | `addons/dcasa_correo/models/politica.py:28-35`; el comprobante de nómina como ejemplo: `addons/dcasa_nomina/models/comprobante.py:97` |
| | Excel con `xlsxwriter` | `addons/dcasa_contabilidad/controllers/main.py:180-183` |
| | Doble factor y registro de accesos | `addons/dcasa_seguridad/__manifest__.py` |
| | Respaldos en el almacenamiento de Cloudflare | `docs/OPERACION.md:32`, `:221` |
| **A13** | **Odoo** | |
| | El gancho `_invoice_paid_hook` se llama al conciliar (también de «en proceso de pago» a «pagada») | `vendor/odoo/addons/account/models/account_move_line.py:2788-2794`; `account_move.py:7361` |
| | El pago sabe si está conciliado con el banco | `vendor/odoo/addons/account/models/account_payment.py:50-52` (`is_reconciled`, `is_matched`) |
| | Si el usuario tiene segundo factor | `vendor/odoo/addons/auth_totp/models/res_users.py:35` (`totp_enabled`) |
| **A14** | **Las campañas del sitio las toca solo Gerencia y quien cambia precios** | `docs/LEEME_PRIMERO.md:264` |

## Anexo B. Cómo se leyó el sistema (y una corrección al encargo)

- «Las ventas atribuidas en tres» (solo Juan / Juan y vendedora / solo vendedora, ventana de 30 días) **no están en
  `tablero.py`** sino en el panel de Juan (A11). Es una atribución por conversación, no por documento, y por eso la
  comisión web no la usa: usa el origen del pedido.
- Dos de las tres piezas que la comisión necesita **ya existen** en el sistema (el libro inmutable y las reglas
  versionadas, A3; el «pagada por completo y qué día», A5). La parte nueva de verdad es el **reparto entre personas**, la
  **propuesta con aprobación** y el **sello mensual**.
- No se corrió ni se cambió ningún código: esta fase solo leyó el sistema y escribió este documento.
