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

«Sí» = cuenta. «Decide Gerencia» = queda como parámetro: **hasta que Gerencia lo conteste, esa venta aparece en el
estado como «en duda» y no suma al monto**; así se ve cuánto dinero depende de cada decisión.

| Caso | ¿Cuenta? | Por qué |
|---|---|---|
| Pedido de la web pagado con pasarela (Tilopay, Yappy oficial, futuras) | **Sí** | Nació en la web y la pasarela es solo el medio. Cuenta cuando la factura queda pagada por completo. |
| Pedido de la web pagado con transferencia o Yappy a mano | **Sí** | Igual: lo registra Caja y cuenta cuando la factura queda completa. Hoy el sitio cobra así (A7). |
| «Pago en la tienda» (apartado por la web, se paga en el local) | **Decide Gerencia** (recomiendo **sí**) | El pedido nació en la web y la web trajo la compra, pero el cobro y la atención son del local. Opciones: sí; no; sí solo si paga dentro del plazo del apartado. |
| Abonos de un apartado | **Solo cuando termina de pagarse** | Mismo criterio del bono por meta (A1): los abonos a medias no suman; si el apartado vence y se anula, no cuenta nada. No se paga «por pedazos»: complica y hay que deshacerlo si se devuelve. |
| Pedido de la web que una vendedora edita o termina por WhatsApp | **Sí** (sigue siendo web) | El pedido es el mismo. El estado lo marca «atendido por vendedora» para medirlo. Ojo con la meta de la vendedora: ver P4. |
| Empezó con Andrés (chat de la tienda) y se cerró en tienda | **Sí si se cerró sobre ese mismo pedido**; **No** si la vendedora armó una cotización nueva aparte | Andrés trabaja sobre el carrito real de la tienda (A8). Lo que decide es el documento que se factura, no la conversación. |
| Empezó con Andrés y la cotización la armó Juan (WhatsApp) | **No** | Juan crea cotizaciones con origen «Chatbot» (A6), otro canal que ya se mide en el panel de Juan. Queda un interruptor apagado por si Gerencia lo quiere (futuro). |
| Cotización de la web pagada en la tienda | Igual que «Pago en la tienda» | Mismo pedido, mismo origen. |
| Factura que junta pedidos de varios orígenes | **Solo las líneas del pedido web** | La etiqueta de la factura da prioridad al chatbot sobre la web (A6); la comisión no se fía de esa etiqueta. |
| Devolución o nota de crédito | **Resta** | En el mes en que se hace (asiento contrario con motivo). Cuenta también la nota que se aplicó suelta, sin enlazar a la factura (como en el bono por meta, A1). Parcial: resta lo devuelto. |
| Devolución de una venta cuyo mes ya se pagó | **Resta en el mes en que ocurre**; si el saldo queda negativo, **se arrastra** | Nunca se descuenta de una planilla sin que Gerencia lo decida. Distinto del bono por meta, que no descuenta lo ya pagado (A1); aquí se propone lo contrario porque el libro lo permite sin esfuerzo. |
| Pago revertido (contracargo) o factura que vuelve a borrador o se cancela | **Resta** | La revisión nocturna lo detecta (como hace el programa de vendedores, A3) y asienta el reverso. |
| Pedido cancelado | **No** | No hay factura pagada. Si ya había contado y se cancela la factura, se reversa. |
| Factura sin pagar o pagada en parte | **No** (todavía) | Sale en «Pendientes de cobro» como información, sin dinero. |
| Descuentos y premios de Socios | **Se cuenta lo que entró** | El premio es una línea negativa que baja la base (A9); el descuento ya viene en el precio. Recomendado: neto, igual que el programa de vendedores. |
| Precio de campaña (Black Friday, etc.) | **Sí, al precio cobrado** | No hay un precio aparte. Ojo: quienes reciben también arman las campañas (sección 7). |
| Cargo de envío | **No** (recomiendo) | Es un costo que se traspasa al cliente, no venta del sitio; además el envío que suma el chat puede irse al pagar. Socios hace lo mismo con su base (A9). Se identifica por la línea de entrega y el producto de flete. |
| ITBMS | **No entra en la base** | Criterio contable vigente: ventas sin ITBMS (LEEME_PRIMERO §1). La comisión que se paga tampoco lleva ITBMS. |
| Comisión de la pasarela | **No se resta** (hoy) | No se sabe por venta: la contadora la ve en el banco. Queda reservado el interruptor para cuando cada pago la guarde. |
| Compra de una de las personas que reciben | **No** | Misma regla «compra propia» del programa de vendedores (A3). |
| Facturas cargadas del sistema anterior o anteriores a la primera versión | **No** | «Solo hacia adelante», igual que el bono por meta (A1). |
| Venta financiada (Tafi, Crediviva) | **Sí**, al quedar pagada la factura | La financiera es una forma de pago (A7). Cómo se cruza lo que deposita después es asunto de la contadora. |
| Pedido al que después le cambian el origen a mano | **No** | Cuenta el testigo escrito al crear el pedido; el cambio dispara una alerta (sección 7). |

**Decisiones que quedan como parámetro de Gerencia** (todas vienen sin responder y se anotan en cada versión de las
reglas): qué hacer con «Pago en la tienda»; si el chatbot cuenta (de fábrica, no); si el envío cuenta (de fábrica, no);
si se resta la comisión de la pasarela (de fábrica, no). El resto de la tabla son criterios fijos de medición.
