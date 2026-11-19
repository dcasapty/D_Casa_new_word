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
Se reparte entre las personas de la lista según su porcentaje de reparto; el centavo que sobre va siempre a la
primera persona de la lista, para que la suma de las partes sea exactamente el total.

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
  ventas», A1) y por eso quien cambia de departamento pierde el bono; aquí no pasa.
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
