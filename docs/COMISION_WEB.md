# La comisión del sitio web (`dcasa_comision_web`)

Decisión de Gerencia del 2026-11-19. Diseño y razones: [PLAN_COMISION_WEB.md](PLAN_COMISION_WEB.md). Este documento
explica **cómo funciona hoy**, en palabras para administración.

> **El módulo nace vacío.** No trae ningún porcentaje, ninguna tarifa ni ninguna persona. Mientras Gerencia no guarde la
> primera versión de las reglas, el sistema **solo mide** las ventas por internet. Nada se paga solo.

## En una frase

Cada venta que sale del sitio web (y quedó pagada por completo) se mide como las de una sucursal; con un porcentaje fijo
de esas ventas, y una tarifa fija por mantener la plataforma, se le va anotando a cada persona lo que le toca; cuando
administración quiere, arma una **liquidación** del periodo que elija, alguien la aprueba y se paga.

## Dónde está

En la app **Nómina › Comisión del sitio web** (solo Gerencia y quien administra la nómina; el administrador técnico solo,
la vendedora, Caja y Marketing no lo ven ni por enlace):

| Pantalla | Para qué |
|---|---|
| **Ventas del sitio** | Una fila por factura del sitio pagada por completo: cómo llegó, cómo pagó, lo vendido, envío, devoluciones, base y comisión. Lista, **gráfico y tabla por mes** (para medir el sitio como una sucursal) y **Excel** con «Exportar». |
| **Liquidaciones** | Armar, aprobar y marcar como pagada la comisión de un periodo. |
| **Quiénes reciben** | La lista de la versión que rige hoy, con el reparto y lo que se le debe a cada quien. Desde aquí se cambia la lista. |
| **Libro** | Todo lo que se ha anotado, por persona. No se edita ni se borra. |
| **Reglas** | Las versiones: porcentaje, tarifa fija, cómo se arma la base y quiénes reciben. |

## Qué es una «venta online»

Hay **una sola definición** en todo el sistema (`dcasa_base/models/venta_online.py`). La usan la comisión del sitio, el bono
por meta, el Inicio de la vendedora y el programa de vendedores.

| Caso | ¿Es venta online? | Cómo se sabe |
|---|---|---|
| Alguien compra en la página web | **Sí** | El pedido nació en la tienda en línea (`dcasa_nacio_en_web`, que se escribe una vez al crear el pedido). |
| Alguien cotiza en la página y llega a la tienda con esa cotización («Pago en la tienda», apartado) | **Sí** | Es el mismo pedido: nació en la página. |
| Todas las ventas de **Andrés** (el chat de la tienda) | **Sí** | Andrés trabaja sobre el carrito real: cada vez que toca el carrito lo marca (`dcasa_via_andres`). Cuenta aunque después la cierre una vendedora. |
| Entra al chat de **Juan**, Juan lo manda a la página o al catálogo y **compra solo** | **Sí** | Nació en la página y, en los 30 días antes de confirmar, ninguna vendedora le escribió por el chat de Juan. |
| Entra al chat de **Juan** y lo **atiende una vendedora** (aunque ella le mande el enlace después) | **No** | Al confirmar el pedido se mira el chat de Juan: si una vendedora le escribió al cliente en los 30 días anteriores, la venta la llevó ella (`dcasa_llevada_por_vendedora`). |
| Lo que se arma en la tienda física, en Ventas o en el Punto de Venta | **No** | No nació en la página. |
| La cotización que arma **Juan** y el cliente paga | **No** (por ahora) | No nació en la página. Ver «Por decidir» más abajo. |

Las tres marcas se escriben **una vez, por código**, y nadie las cambia a mano (ni con `sudo()`): `website_id` sí se puede
cambiar después, por eso el origen se guarda aparte al crear el pedido. Los pedidos que ya existían se marcaron una sola vez
al instalar. Si una factura junta un pedido online con otro de la tienda, solo cuentan como online las líneas del pedido
online.

## Lo que cambió para las vendedoras (solo hacia adelante)

**Las vendedoras nunca reciben nada por una venta online.** Desde el día en que Gerencia ponga en vigencia la primera
versión de las reglas (el «Rige desde» de esa versión), una venta online:

* **no cuenta para el bono por meta** de la vendedora que la confirmó o facturó, ni su nota de crédito resta;
* **no suma al avance** que ella ve en su Inicio («Tu meta del mes» y «Vendido hoy»), y en el Inicio de Gerencia se atribuye
  a «Sin vendedora» en vez de a la vendedora del pedido;
* **no da comisión del programa de vendedores** (queda escrita con el motivo «venta del sitio web» y cero puntos).

**Nada es retroactivo**: se mira el día en que se cobró la venta (el Inicio de Gerencia mira el de la factura). Lo cobrado
antes de ese día cuenta como siempre, y sus devoluciones también. **El mes en curso queda partido**: si la primera versión
rige el 15, lo cobrado del 1 al 14 cuenta como antes y lo cobrado desde el 15 ya no cuenta lo online. **Sin versión de
reglas, nada de esto cambia.** Lo de la tienda, y lo de Juan que atiende una vendedora, cuenta igual que hoy.

## Las reglas (una versión por cambio)

**Nómina › Comisión del sitio web › Reglas › Nueva versión.** Cada versión dice, desde cuándo rige:

* **Porcentaje** de cada venta del sitio (fijo; **no es un bono por meta**: se paga aunque no se llegue a ninguna meta). En 0
  no hay porcentaje: las ventas se miden igual.
* **Tarifa fija** por mantener la plataforma (un monto fijo que sale siempre de la empresa) y **cada cuánto se anota**:
  cada mes (por defecto), cada quincena o cada semana. En 0 no hay tarifa. La tarifa se anota **el primer día de cada
  periodo** (el día 1; los días 1 y 16; cada lunes) con la versión que regía a las 00:00 de ese día. La primera tarifa de
  una versión es la del primer periodo que empieza cuando ya rige (si rige un 10, la del mes empieza el día 1 del mes
  siguiente; si hace falta algo distinto, se anota un ajuste con motivo).
* **Cómo se arma la base**, con cinco interruptores en palabras sencillas. Al cambiar uno, el **ejemplo con números de
  mentira** de la pantalla se mueve para que se vea qué entra y qué no:

| Interruptor | Recomendado de fábrica | La otra posición |
|---|---|---|
| ITBMS | **Sin ITBMS**: antes del impuesto | Con ITBMS: después del impuesto |
| Envío | **No cuenta el envío** | Cuenta el envío |
| Descuentos | **Después de los descuentos**: con lo que de verdad se cobró (premios y cupones ya restados) | Antes de los descuentos: con el precio de lista |
| Devoluciones | **Se resta** lo que el cliente devuelve | No se resta |
| Comisión de la pasarela | **No se resta** | Se resta (hoy ninguna pasarela guarda cuánto cobra: el interruptor ya está listo para cuando la guarde) |

* **Quiénes reciben**: se eligen entre los **empleados de Nómina** (no depende del departamento: si la persona cambia de
  departamento, esto no cambia) y a cada quien le toca un porcentaje del reparto; **tiene que sumar 100 %**. Los centavos
  que sobran van, de uno en uno y siempre en el mismo orden, a las primeras personas de la lista.

**Una versión guardada no se edita ni se borra**; un cambio es una versión nueva, y solo rige hacia adelante (no se acepta una
fecha que ya pasó). Lo ya anotado en el libro **nunca se recalcula**. Pausar es guardar una versión con porcentaje y tarifa
en 0.

## La base y el porcentaje, paso a paso

La base de una venta es: **lo vendido** (los muebles, sin ITBMS y con el descuento de cada línea) más o menos lo que digan
los interruptores. La **comisión** es la base × porcentaje ÷ 100, en centavos (mitad hacia arriba, como la planilla), y se
reparte entre quienes reciben. Nunca es negativa. Cada venta guarda con qué versión nació.

## Cuándo cuenta una venta y cómo se corrige

* Cuenta cuando su factura queda **pagada por completo** (o «en proceso de pago»), con la misma definición del bono por
  meta y del Inicio (hay una prueba que verifica que las dos dan el mismo día). Los abonos a medias no cuentan.
* Una **devolución** (nota de crédito, enlazada o aplicada suelta) resta en el libro **en el mes en que ocurre**; el mes de la
  venta no cambia nunca.
* Un **pago revertido**, una factura **anulada** o vuelta a borrador **reversa** lo anotado. Si vuelve a quedar pagada, se
  repone.
* **Un error de la comisión nunca hace fallar un cobro ni una factura**: corre dentro de un savepoint y el error queda en el
  registro. Cada noche un **barrido** anota lo que el gancho no alcanzó y **compara el libro con la verdad** de cada venta,
  asentando la diferencia como fila contraria.
* **Solo hacia adelante**: una venta cobrada antes de que rija la primera versión se mide y **nunca cobra**.

## El libro

Una fila por persona y por hecho, **en centavos enteros**. El **saldo es la suma de las filas** (no existe una columna de
saldo). Tipos: venta, devolución, reverso, tarifa fija, ajuste y liquidación. **No se edita ni se borra** (ni con `sudo()` ni
por RPC): una corrección es otra fila con la cifra contraria, su motivo y su autor. Cada fila guarda el **mes de Panamá** en
que se anotó y ese mes no se mueve: lo anotado en noviembre queda en noviembre.

Hay **dos conceptos**, aparte en el libro y en cada liquidación: el **porcentaje de las ventas** y la **tarifa fija**.

## Liquidaciones: propuesta → aprobación → pagada

**Nómina › Comisión del sitio web › Liquidaciones › Nuevo.**

1. **Propuesta.** Se elige el periodo que se quiera (desde y hasta, **cualquiera**: semana, quincena, mes; con atajos «este
   mes», «el mes pasado», «primera quincena de este mes», «segunda quincena del mes pasado», «esta semana»…) y se toca
   **Armar**. Se junta **todo lo que se debe hasta esa fecha y todavía no se había liquidado**, por persona y concepto.
   Se puede armar de nuevo las veces que haga falta.
2. **Aprobada.** La aprueba una persona de Gerencia o de Nómina **que no figure entre quienes cobran en esa
   liquidación**: es la **única protección** y es automática (la pantalla lo explica con una frase amable). Queda quién y
   cuándo. Al aprobar se anota en el libro una fila negativa de liquidación por persona y concepto: la plata sale del
   saldo, así que **nunca se paga dos veces lo mismo**, aunque los periodos se solapen o haya dos propuestas a la vez
   (la segunda en aprobarse pide armarse otra vez). Una aprobada **no se edita**.
3. **Pagada.** Se escribe la fecha y la referencia del pago (transferencia, cheque, recibo) y se marca como pagada. El
   sistema **no mueve dinero**: lo anota.
4. **Cancelada.** Una aprobada que todavía no se pagó se cancela con su motivo; se anula con filas contrarias y lo que se
   debe vuelve al saldo. Una propuesta se cancela o se borra sin tocar el libro.

Si el saldo de alguien es negativo (devoluciones que superaron lo ganado), hoy se le paga cero, se avisa y el saldo sigue
para la próxima liquidación: **nunca se le descuenta a nadie por la planilla sin que Gerencia lo decida**.
**Nada se paga solo**: ningún proceso automático aprueba ni paga.

## Cómo se paga (y lo que NO es)

Decisión de Gerencia: **la comisión no cuenta como salario**. Se paga **sin descuentos de planilla** (como los reembolsos).
**Conviene que la contadora deje por escrito el tratamiento** (anótese; no bloquea nada). Enviar una liquidación aprobada a la
planilla como línea sin descuentos queda como siguiente paso (ver abajo); mientras tanto basta marcarla como pagada con su
referencia.

## Quién puede qué

| Quién | Qué ve y hace |
|---|---|
| Gerencia y quien administra la nómina | Todo: ven las cinco pantallas, guardan versiones de las reglas, arman, aprueban (menos donde cobran), pagan y cancelan liquidaciones. |
| El administrador técnico (solo) | **Nada** de la comisión (como siempre, puede darse roles: es el límite honesto de cualquier sistema). |
| Vendedora, Caja, Marketing, el público | Nada: ni el menú ni por enlace. |

## Pendiente a propósito (anotado como futuro)

* **Sello mensual por correo y huella encadenada** del diseño original: Gerencia pidió una sola protección, así que no están.
* Enviar una liquidación aprobada a la **planilla** como línea sin descuentos.
* Un resumen de la comisión en el **Inicio** y una herramienta de **Brian** de solo lectura.
* Escalones, metas, topes y porcentajes por producto o canal; restar la comisión de la pasarela automáticamente (el
  interruptor ya existe: falta que cada pasarela guarde su cobro en `payment.transaction.dcasa_comision_pasarela`).
* Informes de «Pendientes de cobro» y «Pagos del sitio sin factura todavía».

## Por decidir o verificar con Gerencia y la contadora

1. **Programa de vendedores (códigos VEN).** El enlace `dcasapty.com/v/VEN…` lleva a la tienda web. Con esta regla, esas
   compras ya no dan puntos de vendedor (ni a empleados ni a gente de afuera). ¿Es lo que se quiere, o solo las vendedoras de
   la tienda?
2. **Juan arma la cotización y el cliente paga.** Hoy no cuenta como venta online (no nació en la página). ¿Debe contar?
3. **Cuántos días hacia atrás se mira el chat de Juan** para saber si una vendedora llevó la venta: hoy 30, los mismos con que
   el panel de Juan atribuye ventas.
4. **Andrés pasa al cliente a una vendedora por WhatsApp y ella cierra:** hoy cuenta como venta de Andrés (online).
5. **La contadora**: tratamiento por escrito de la comisión y de la tarifa fija (no son salario) y de las devoluciones
   posteriores a un pago.
6. **Compras de quienes reciben:** el diseño las excluía; con «una sola protección» hoy no se excluyen.
7. **Primera tarifa:** se anota el primer día del periodo siguiente a que rige la versión; si hace falta una parcial, es un ajuste.
